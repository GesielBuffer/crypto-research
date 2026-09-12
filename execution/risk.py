from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from execution.models import OrderIntent


class RiskRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class RiskLimits:
    approved_strategies: frozenset[str]
    max_notional_per_order: Decimal = Decimal("100")
    max_open_positions: int = 1
    max_leverage: int = 1
    max_daily_loss: Decimal = Decimal("10")
    max_market_data_age: timedelta = timedelta(seconds=30)


@dataclass(frozen=True)
class RiskSnapshot:
    open_symbols: frozenset[str] = frozenset()
    realized_pnl_today: Decimal = Decimal("0")
    kill_switch: bool = False


class RiskEngine:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def validate(
        self,
        intent: OrderIntent,
        snapshot: RiskSnapshot,
        *,
        now: datetime | None = None,
    ) -> None:
        current_time = now or datetime.now(timezone.utc)
        reasons = []
        if snapshot.kill_switch:
            reasons.append("kill switch is active")
        if intent.strategy_id not in self.limits.approved_strategies:
            reasons.append("strategy is not approved")
        if intent.quantity <= 0 or intent.reference_price <= 0:
            reasons.append("quantity and price must be positive")
        if intent.leverage < 1 or intent.leverage > self.limits.max_leverage:
            reasons.append("leverage exceeds limit")
        if intent.notional > self.limits.max_notional_per_order:
            reasons.append("order notional exceeds limit")
        if snapshot.realized_pnl_today <= -self.limits.max_daily_loss:
            reasons.append("daily loss limit reached")
        if (
            intent.symbol not in snapshot.open_symbols
            and len(snapshot.open_symbols) >= self.limits.max_open_positions
        ):
            reasons.append("open position limit reached")
        market_time = intent.market_data_time
        if market_time.tzinfo is None:
            reasons.append("market data timestamp must be timezone-aware")
        elif current_time - market_time > self.limits.max_market_data_age:
            reasons.append("market data is stale")
        if reasons:
            raise RiskRejected("; ".join(reasons))
