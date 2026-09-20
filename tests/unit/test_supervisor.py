import unittest
from datetime import datetime, timezone
from decimal import Decimal

from execution.models import BreakEvenPolicy, OrderIntent, PositionProtection, Side
from execution.paper import PaperExchange
from execution.risk import RiskEngine, RiskLimits
from execution.service import TradingService
from execution.supervisor import (
    PositionSupervisor,
    SupervisorConfig,
    SupervisorUnavailable,
)


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def intent(*, enabled=True):
    return OrderIntent(
        strategy_id="approved-v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=Decimal("0.001"),
        reference_price=Decimal("50000"),
        leverage=1,
        client_order_id="apv1-BTC-20260920T000000Z",
        market_data_time=NOW,
        protection=PositionProtection(
            stop_loss_price=Decimal("49500"),
            take_profit_price=Decimal("51000"),
            break_even=BreakEvenPolicy(enabled=enabled),
        ),
    )


class TransientMarkPriceExchange(PaperExchange):
    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    def get_mark_price(self, symbol):
        if self.failures:
            self.failures -= 1
            raise ConnectionError("temporary market data failure")
        return super().get_mark_price(symbol)


class PositionSupervisorTests(unittest.TestCase):
    def service_for(self, exchange):
        return TradingService(
            exchange,
            RiskEngine(RiskLimits(approved_strategies=frozenset({"approved-v1"}))),
        )

    def test_disabled_policy_exits_without_reading_market_data(self):
        exchange = PaperExchange()
        supervisor = PositionSupervisor(self.service_for(exchange))
        result = supervisor.run(intent(enabled=False), should_stop=lambda: False)
        self.assertEqual(result.reason, "policy_disabled")
        self.assertEqual(result.cycles, 0)

    def test_cycle_limit_is_deterministic_before_trigger(self):
        exchange = PaperExchange()
        order = intent()
        service = self.service_for(exchange)
        service.execute(order, now=NOW)
        exchange.set_mark_price(order.symbol, Decimal("50400"), observed_at=NOW)
        supervisor = PositionSupervisor(
            service,
            sleeper=lambda _: None,
            clock=lambda: NOW,
        )
        result = supervisor.run(
            order,
            should_stop=lambda: False,
            max_cycles=2,
        )
        self.assertEqual(result.reason, "cycle_limit")
        self.assertEqual(result.cycles, 2)

    def test_transient_failure_uses_backoff_then_recovers(self):
        exchange = TransientMarkPriceExchange(failures=2)
        order = intent()
        service = self.service_for(exchange)
        service.execute(order, now=NOW)
        exchange.set_mark_price(order.symbol, Decimal("50500"), observed_at=NOW)
        delays = []
        supervisor = PositionSupervisor(
            service,
            SupervisorConfig(max_consecutive_failures=3),
            sleeper=delays.append,
            clock=lambda: NOW,
        )
        result = supervisor.run(order, should_stop=lambda: False)
        self.assertEqual(result.reason, "protection_adjusted")
        self.assertEqual(result.transient_failures, 2)
        self.assertEqual(delays, [1.0, 2.0])

    def test_transient_failure_limit_stops_the_supervisor(self):
        exchange = TransientMarkPriceExchange(failures=3)
        order = intent()
        service = self.service_for(exchange)
        service.execute(order, now=NOW)
        supervisor = PositionSupervisor(
            service,
            SupervisorConfig(max_consecutive_failures=3),
            sleeper=lambda _: None,
            clock=lambda: NOW,
        )
        with self.assertRaisesRegex(SupervisorUnavailable, "failure limit"):
            supervisor.run(order, should_stop=lambda: False)

    def test_stop_request_exits_without_a_cycle(self):
        supervisor = PositionSupervisor(self.service_for(PaperExchange()))
        result = supervisor.run(intent(), should_stop=lambda: True)
        self.assertEqual(result.reason, "stop_requested")
        self.assertEqual(result.cycles, 0)


if __name__ == "__main__":
    unittest.main()
