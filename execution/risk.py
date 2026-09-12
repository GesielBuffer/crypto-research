from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re

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
    max_clock_skew: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if self.max_notional_per_order <= 0:
            raise ValueError("max_notional_per_order must be positive")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if self.max_leverage < 1:
            raise ValueError("max_leverage must be at least 1")
        if self.max_daily_loss <= 0:
            raise ValueError("max_daily_loss must be positive")
        if self.max_market_data_age <= timedelta(0) or self.max_clock_skew < timedelta(0):
            raise ValueError("market data timing limits are invalid")


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
        if current_time.tzinfo is None:
            raise ValueError("current time must be timezone-aware")
        if snapshot.kill_switch:
            reasons.append("kill switch is active")
        if intent.strategy_id not in self.limits.approved_strategies:
            reasons.append("strategy is not approved")
        valid_prices = (
            intent.quantity.is_finite()
            and intent.reference_price.is_finite()
            and intent.quantity > 0
            and intent.reference_price > 0
        )
        if not valid_prices:
            reasons.append("quantity and price must be positive")
        if not re.fullmatch(r"[A-Z0-9]{3,20}", intent.symbol):
            reasons.append("symbol format is invalid")
        if not re.fullmatch(r"[.A-Za-z0-9_:/-]{1,32}", intent.client_order_id):
            reasons.append("client_order_id format is invalid")
        if intent.leverage < 1 or intent.leverage > self.limits.max_leverage:
            reasons.append("leverage exceeds limit")
        if valid_prices and intent.notional > self.limits.max_notional_per_order:
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
        elif market_time - current_time > self.limits.max_clock_skew:
            reasons.append("market data timestamp is in the future")
        if reasons:
            raise RiskRejected("; ".join(reasons))
