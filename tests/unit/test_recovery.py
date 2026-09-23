import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from execution.journal import JsonlOrderJournal
from execution.models import BreakEvenPolicy, Fill, OrderIntent, PositionProtection, Side
from execution.paper import PaperExchange
from execution.recovery import JournalRecovery
from execution.risk import RiskEngine, RiskLimits
from execution.service import TradingService


NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def intent():
    return OrderIntent(
        strategy_id="approved-v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=Decimal("0.001"),
        reference_price=Decimal("50000"),
        leverage=1,
        client_order_id="apv1-BTC-20260923T000000Z",
        market_data_time=NOW,
        protection=PositionProtection(
            stop_loss_price=Decimal("49500"),
            take_profit_price=Decimal("51000"),
            break_even=BreakEvenPolicy(
                enabled=True,
                activation_r_multiple=Decimal("1.25"),
                cost_buffer_rate=Decimal("0.0006"),
            ),
        ),
    )


class CountingPaperExchange(PaperExchange):
    def __init__(self):
        super().__init__()
        self.entry_submissions = 0

    def submit_market(self, order_intent):
        self.entry_submissions += 1
        return super().submit_market(order_intent)


class JournalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = JsonlOrderJournal(Path(self.directory.name) / "orders.jsonl")
        self.exchange = CountingPaperExchange()
        self.service = TradingService(
            self.exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
            self.journal,
        )

    def recovery(self):
        return JournalRecovery(self.service, self.journal)

    def test_journal_round_trips_complete_intent(self):
        order = intent()
        self.journal.record_intent(order)
        self.assertEqual(self.journal.intent_for(order.client_order_id), order)
        self.assertEqual(self.journal.intents(), [order])

    def test_remote_fill_is_recovered_and_protected_without_new_entry(self):
        order = intent()
        self.journal.record_intent(order)
        self.exchange.submit_market(order)
        self.exchange.entry_submissions = 0

        report = self.recovery().recover()

        self.assertTrue(report.ready)
        self.assertEqual(report.items[0].status, "protected")
        self.assertEqual(self.exchange.entry_submissions, 0)
        self.assertIsNotNone(self.exchange.find_protection(order))
        self.assertIsNotNone(self.journal.fill_for(order.client_order_id))

    def test_unknown_pending_intent_is_reported_without_submission(self):
        order = intent()
        self.journal.record_intent(order)

        report = self.recovery().recover()

        self.assertFalse(report.ready)
        self.assertEqual(report.items[0].status, "unresolved")
        self.assertEqual(self.exchange.entry_submissions, 0)

    def test_local_fill_missing_from_exchange_is_divergence(self):
        order = intent()
        self.journal.record_intent(order)
        self.journal.record_fill(Fill.from_intent(order))

        report = self.recovery().recover()

        self.assertFalse(report.ready)
        self.assertEqual(report.items[0].status, "divergence")
        self.assertEqual(self.exchange.entry_submissions, 0)

    def test_exchange_side_close_is_recovered_and_recorded(self):
        order = intent()
        self.journal.record_intent(order)
        remote_fill = self.exchange.submit_market(order)
        self.journal.record_fill(remote_fill)
        self.exchange.simulate_protection_fill(order)
        self.exchange.entry_submissions = 0

        report = self.recovery().recover()

        self.assertTrue(report.ready)
        self.assertEqual(report.items[0].status, "closed")
        self.assertEqual(
            self.journal.closed_entry_ids(),
            {order.client_order_id},
        )
        self.assertEqual(self.exchange.entry_submissions, 0)

    def test_previously_closed_entry_requires_no_exchange_action(self):
        order = intent()
        self.journal.record_intent(order)
        self.journal.record_position_closed(order.client_order_id)

        report = self.recovery().recover()

        self.assertTrue(report.ready)
        self.assertEqual(report.items[0].status, "closed")
        self.assertEqual(self.exchange.entry_submissions, 0)

    def test_report_is_serializable_and_counts_blockers(self):
        self.journal.record_intent(intent())
        payload = self.recovery().recover().as_dict()
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["blockers"], 1)
        self.assertEqual(payload["items"][0]["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
