from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re

from execution.models import Fill, OrderIntent, Side


class RiskRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class RiskLimits:
    approved_strategies: frozenset[str]
    max_notional_per_order: Decimal = Decimal("100")
    max_open_positions: int = 1
    max_leverage: int = 1
    max_daily_loss: Decimal = Decimal("10")
    max_loss_per_order: Decimal = Decimal("2")
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
        if self.max_loss_per_order <= 0:
            raise ValueError("max_loss_per_order must be positive")
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
        protection = intent.protection
        protection_prices_valid = protection is not None and (
            protection.stop_loss_price.is_finite()
            and protection.take_profit_price.is_finite()
            and protection.stop_loss_price > 0
            and protection.take_profit_price > 0
        )
        if not protection_prices_valid:
            reasons.append("protection prices must be positive")
        elif intent.side.value == "BUY" and not (
            protection.stop_loss_price
            < intent.reference_price
            < protection.take_profit_price
        ):
            reasons.append("long protection prices must bracket the entry")
        elif intent.side.value == "SELL" and not (
            protection.take_profit_price
            < intent.reference_price
            < protection.stop_loss_price
        ):
            reasons.append("short protection prices must bracket the entry")
        elif valid_prices:
            planned_loss = (
                abs(intent.reference_price - protection.stop_loss_price)
                * intent.quantity
            )
            if planned_loss > self.limits.max_loss_per_order:
                reasons.append("planned stop loss exceeds per-order loss limit")
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

    def validate_fill_protection(self, intent: OrderIntent, fill: Fill) -> None:
        """Reject protection that no longer brackets the actual execution price."""
        protection = intent.protection
        if fill.side is Side.BUY:
            bracketed = (
                protection.stop_loss_price
                < fill.price
                < protection.take_profit_price
            )
        else:
            bracketed = (
                protection.take_profit_price
                < fill.price
                < protection.stop_loss_price
            )
        actual_planned_loss = (
            abs(fill.price - protection.stop_loss_price) * fill.quantity
        )
        reasons = []
        if not bracketed:
            reasons.append("protection no longer brackets the actual fill")
        if actual_planned_loss > self.limits.max_loss_per_order:
            reasons.append("actual fill makes planned loss exceed the limit")
        if reasons:
            raise RiskRejected("; ".join(reasons))
