import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from execution.journal import JsonlOrderJournal
from execution.models import OrderIntent, Side
from execution.paper import PaperExchange
from execution.risk import RiskEngine, RiskLimits, RiskRejected, RiskSnapshot
from execution.service import TradingService


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class FailingExchange:
    def snapshot(self):
        return RiskSnapshot()

    def submit_market(self, order_intent):
        raise ConnectionError("simulated network failure")


def intent(**overrides):
    values = {
        "strategy_id": "approved-v1",
        "symbol": "BTCUSDT",
        "side": Side.BUY,
        "quantity": Decimal("0.001"),
        "reference_price": Decimal("50000"),
        "leverage": 1,
        "client_order_id": "approved-v1-BTCUSDT-20260912T000000Z",
        "market_data_time": NOW,
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

    def test_unapproved_strategy_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "not approved"):
            self.service.execute(intent(strategy_id="C2_FAILED"), now=NOW)

    def test_stale_market_data_is_blocked(self):
        with self.assertRaisesRegex(RiskRejected, "stale"):
            self.service.execute(
                intent(market_data_time=NOW - timedelta(minutes=1)), now=NOW
            )

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
                {"approved-v1-BTCUSDT-20260912T000000Z"},
            )
