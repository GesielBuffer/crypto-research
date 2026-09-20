import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from execution.journal import JsonlOrderJournal
from execution.models import BreakEvenPolicy, OrderIntent, PositionProtection, Side
from execution.paper import PaperExchange
from execution.risk import RiskEngine, RiskLimits, RiskRejected, RiskSnapshot
from execution.service import (
    IdempotencyConflict,
    PositionProtectionFailed,
    ReconciliationRequired,
    TradingService,
    UnprotectedPositionEmergency,
)


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class FailingExchange:
    def snapshot(self):
        return RiskSnapshot()

    def submit_market(self, order_intent):
        raise ConnectionError("simulated network failure")

    def find_fill(self, order_intent):
        return None


class AcceptedThenTimeoutExchange(PaperExchange):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    def submit_market(self, order_intent):
        fill = super().submit_market(order_intent)
        if not self.failed_once:
            self.failed_once = True
            raise TimeoutError("response lost after exchange accepted order")
        return fill


class ProtectionFailureExchange(PaperExchange):
    def submit_protection(self, order_intent, entry_fill):
        raise ConnectionError("simulated protection failure")


class TotalProtectionFailureExchange(ProtectionFailureExchange):
    def emergency_close(self, order_intent, entry_fill):
        raise ConnectionError("simulated emergency close failure")


class ProtectionLookupFailureExchange(PaperExchange):
    def find_protection(self, order_intent):
        raise ConnectionError("simulated protection lookup failure")


class SlippedFillExchange(PaperExchange):
    def submit_market(self, order_intent):
        fill = super().submit_market(order_intent)
        slipped = type(fill)(
            client_order_id=fill.client_order_id,
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            price=Decimal("51100"),
            filled_at=fill.filled_at,
        )
        self._fills[order_intent.client_order_id] = slipped
        return slipped


class BreakEvenReplacementFailureExchange(PaperExchange):
    def replace_stop(self, order_intent, entry_fill, current, new_stop_price):
        raise TimeoutError("simulated stop replacement timeout")


def intent(**overrides):
    values = {
        "strategy_id": "approved-v1",
        "symbol": "BTCUSDT",
        "side": Side.BUY,
        "quantity": Decimal("0.001"),
        "reference_price": Decimal("50000"),
        "leverage": 1,
        "client_order_id": "apv1-BTC-20260912T000000Z",
        "market_data_time": NOW,
        "protection": PositionProtection(
            stop_loss_price=Decimal("49500"),
            take_profit_price=Decimal("51000"),
        ),
    }
    values.update(overrides)
    return OrderIntent(**values)


class ExecutionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.exchange = PaperExchange()
        self.service = TradingService(
            self.exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )

    def test_paper_order_is_idempotent(self):
        first = self.service.execute(intent(), now=NOW)
        second = self.service.execute(intent(), now=NOW)
        self.assertEqual(first, second)
        self.assertEqual(self.exchange.snapshot().open_symbols, frozenset({"BTCUSDT"}))
        self.assertIsNotNone(self.exchange.find_protection(intent()))

    def test_disabled_break_even_does_nothing(self):
        order = intent()
        self.service.execute(order, now=NOW)
        self.assertIsNone(
            self.service.advance_to_break_even(order, mark_price=Decimal("50500"))
        )

    def test_supervisor_reads_fresh_mark_price_and_advances_protection(self):
        order = intent(
            protection=PositionProtection(
                stop_loss_price=Decimal("49500"),
                take_profit_price=Decimal("51000"),
                break_even=BreakEvenPolicy(enabled=True),
            )
        )
        self.service.execute(order, now=NOW)
        self.exchange.set_mark_price(
            order.symbol,
            Decimal("50500"),
            observed_at=NOW,
        )
        adjusted = self.service.supervise_position(order, now=NOW)
        self.assertEqual(adjusted.stop_price, Decimal("50000"))

    def test_supervisor_rejects_stale_mark_price(self):
        order = intent(
            protection=PositionProtection(
                stop_loss_price=Decimal("49500"),
                take_profit_price=Decimal("51000"),
                break_even=BreakEvenPolicy(enabled=True),
            )
        )
        self.service.execute(order, now=NOW)
        self.exchange.set_mark_price(
            order.symbol,
            Decimal("50500"),
            observed_at=NOW - timedelta(seconds=31),
        )
        with self.assertRaisesRegex(ReconciliationRequired, "stale"):
            self.service.supervise_position(order, now=NOW)
        self.assertEqual(
            self.exchange.find_protection(order).stop_price,
            Decimal("49500"),
        )

    def test_long_break_even_waits_for_trigger_then_moves_to_economic_price(self):
        order = intent(
            protection=PositionProtection(
                stop_loss_price=Decimal("49500"),
                take_profit_price=Decimal("51000"),
                break_even=BreakEvenPolicy(
                    enabled=True,
                    activation_r_multiple=Decimal("1"),
                    cost_buffer_rate=Decimal("0.001"),
                ),
            )
        )
        self.service.execute(order, now=NOW)
        self.assertIsNone(
            self.service.advance_to_break_even(order, mark_price=Decimal("50499"))
        )
        adjusted = self.service.advance_to_break_even(
            order, mark_price=Decimal("50500")
        )
        self.assertEqual(adjusted.stop_price, Decimal("50050.000"))
        self.assertEqual(
            adjusted.stop_client_order_id,
            self.service.advance_to_break_even(
                order, mark_price=Decimal("50600")
            ).stop_client_order_id,
        )

    def test_short_break_even_is_directionally_symmetric(self):
        order = intent(
            side=Side.SELL,
            protection=PositionProtection(
                stop_loss_price=Decimal("50500"),
                take_profit_price=Decimal("49000"),
                break_even=BreakEvenPolicy(
                    enabled=True,
                    activation_r_multiple=Decimal("1"),
                    cost_buffer_rate=Decimal("0.001"),
                ),
            ),
        )
        self.service.execute(order, now=NOW)
        adjusted = self.service.advance_to_break_even(
            order, mark_price=Decimal("49500")
        )
        self.assertEqual(adjusted.stop_price, Decimal("49950.000"))

    def test_break_even_failure_keeps_existing_protection_and_requires_reconciliation(self):
        exchange = BreakEvenReplacementFailureExchange()
        service = TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )
        order = intent(
            protection=PositionProtection(
                stop_loss_price=Decimal("49500"),
                take_profit_price=Decimal("51000"),
                break_even=BreakEvenPolicy(enabled=True),
            )
        )
        service.execute(order, now=NOW)
        with self.assertRaisesRegex(ReconciliationRequired, "prior protection remains"):
            service.advance_to_break_even(order, mark_price=Decimal("50500"))
        self.assertEqual(exchange.snapshot().open_symbols, frozenset({"BTCUSDT"}))
        self.assertEqual(
            exchange.find_protection(order).stop_price,
            Decimal("49500"),
        )

    def test_break_even_adjustment_is_journaled_once(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = JsonlOrderJournal(Path(directory) / "orders.jsonl")
            service = TradingService(
                self.exchange,
                RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
                journal,
            )
            order = intent(
                protection=PositionProtection(
                    stop_loss_price=Decimal("49500"),
                    take_profit_price=Decimal("51000"),
                    break_even=BreakEvenPolicy(enabled=True),
                )
            )
            service.execute(order, now=NOW)
            service.advance_to_break_even(order, mark_price=Decimal("50500"))
            service.advance_to_break_even(order, mark_price=Decimal("50600"))
            adjustments = [
                row for row in journal.records()
                if row["event"] == "protection_adjustment"
            ]
            self.assertEqual(len(adjustments), 1)

    def test_long_requires_stop_below_and_target_above_entry(self):
        with self.assertRaisesRegex(RiskRejected, "bracket"):
            self.service.execute(
                intent(
                    protection=PositionProtection(
                        stop_loss_price=Decimal("50500"),
                        take_profit_price=Decimal("51000"),
                    )
                ),
                now=NOW,
            )

    def test_short_requires_target_below_and_stop_above_entry(self):
        with self.assertRaisesRegex(RiskRejected, "bracket"):
            self.service.execute(
                intent(
                    side=Side.SELL,
                    protection=PositionProtection(
                        stop_loss_price=Decimal("49000"),
                        take_profit_price=Decimal("48000"),
                    ),
                ),
                now=NOW,
            )

    def test_planned_loss_is_limited(self):
        with self.assertRaisesRegex(RiskRejected, "planned stop loss"):
            self.service.execute(
                intent(
                    quantity=Decimal("0.01"),
                    reference_price=Decimal("10000"),
                    protection=PositionProtection(
                        stop_loss_price=Decimal("9000"),
                        take_profit_price=Decimal("11000"),
                    ),
                ),
                now=NOW,
            )

    def test_protection_failure_immediately_closes_position(self):
        exchange = ProtectionFailureExchange()
        service = TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )
        with self.assertRaises(PositionProtectionFailed):
            service.execute(intent(), now=NOW)
        self.assertEqual(exchange.snapshot().open_symbols, frozenset())
        with self.assertRaisesRegex(PositionProtectionFailed, "already closed"):
            service.execute(intent(), now=NOW)
        self.assertIsNone(exchange.find_protection(intent()))

    def test_protection_lookup_failure_immediately_closes_position(self):
        exchange = ProtectionLookupFailureExchange()
        service = TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )
        with self.assertRaises(PositionProtectionFailed):
            service.execute(intent(), now=NOW)
        self.assertEqual(exchange.snapshot().open_symbols, frozenset())

    def test_fill_outside_protection_bracket_is_closed(self):
        exchange = SlippedFillExchange()
        service = TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )
        with self.assertRaises(PositionProtectionFailed):
            service.execute(intent(), now=NOW)
        self.assertEqual(exchange.snapshot().open_symbols, frozenset())

    def test_double_failure_requires_manual_intervention(self):
        exchange = TotalProtectionFailureExchange()
        service = TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )
        with self.assertRaises(UnprotectedPositionEmergency):
            service.execute(intent(), now=NOW)

    def test_reused_id_with_different_order_is_rejected(self):
        self.service.execute(intent(), now=NOW)
        with self.assertRaises(IdempotencyConflict):
            self.service.execute(intent(quantity=Decimal("0.002")), now=NOW)

    def test_unapproved_strategy_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "not approved"):
            self.service.execute(intent(strategy_id="C2_FAILED"), now=NOW)

    def test_stale_market_data_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "stale"):
            self.service.execute(
                intent(market_data_time=NOW - timedelta(minutes=1)), now=NOW
            )

    def test_future_market_data_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "future"):
            self.service.execute(
                intent(market_data_time=NOW + timedelta(seconds=6)), now=NOW
            )

    def test_invalid_client_order_id_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "client_order_id"):
            self.service.execute(intent(client_order_id="bad id"), now=NOW)

    def test_notional_and_leverage_limits_are_enforced(self):
        with self.assertRaises(RiskRejected):
            self.service.execute(
                intent(quantity=Decimal("1"), leverage=15), now=NOW
            )

    def test_kill_switch_blocks_orders(self):
        self.exchange.activate_kill_switch()
        with self.assertRaisesRegex(RiskRejected, "kill switch"):
            self.service.execute(intent(), now=NOW)

    def test_journal_reconciles_completed_order(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = JsonlOrderJournal(Path(directory) / "orders.jsonl")
            service = TradingService(
                self.exchange,
                RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
                journal,
            )
            service.execute(intent(), now=NOW)
            self.assertEqual(journal.pending_order_ids(), set())

    def test_journal_exposes_interrupted_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = JsonlOrderJournal(Path(directory) / "orders.jsonl")
            service = TradingService(
                FailingExchange(),
                RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
                journal,
            )
            with self.assertRaises(ConnectionError):
                service.execute(intent(), now=NOW)
            self.assertEqual(
                journal.pending_order_ids(),
                {"apv1-BTC-20260912T000000Z"},
            )
            with self.assertRaises(ReconciliationRequired):
                service.execute(intent(), now=NOW)

    def test_timeout_after_acceptance_is_reconciled_without_resubmission(self):
        with tempfile.TemporaryDirectory() as directory:
            exchange = AcceptedThenTimeoutExchange()
            journal = JsonlOrderJournal(Path(directory) / "orders.jsonl")
            service = TradingService(
                exchange,
                RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
                journal,
            )
            with self.assertRaises(TimeoutError):
                service.execute(intent(), now=NOW)
            recovered = service.execute(intent(), now=NOW)
            self.assertEqual(recovered.client_order_id, intent().client_order_id)
            self.assertEqual(journal.pending_order_ids(), set())

    def test_journal_exchange_divergence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = JsonlOrderJournal(Path(directory) / "orders.jsonl")
            journal.record_fill(self.exchange.submit_market(intent()))
            restarted_exchange = PaperExchange()
            service = TradingService(
                restarted_exchange,
                RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
                journal,
            )
            with self.assertRaisesRegex(ReconciliationRequired, "cannot confirm"):
                service.execute(intent(), now=NOW)
