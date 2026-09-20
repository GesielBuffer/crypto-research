from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


def child_order_id(client_order_id: str, purpose: str) -> str:
    """Return a stable Binance-compatible ID without exposing the parent length."""
    digest = hashlib.sha256(client_order_id.encode("utf-8")).hexdigest()[:24]
    return f"px-{digest}-{purpose}"


@dataclass(frozen=True)
class BreakEvenPolicy:
    """Optional rule for moving a protected position to economic break-even."""

    enabled: bool = False
    activation_r_multiple: Decimal = Decimal("1")
    cost_buffer_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if (
            not self.activation_r_multiple.is_finite()
            or self.activation_r_multiple <= 0
        ):
            raise ValueError("activation_r_multiple must be positive")
        if (
            not self.cost_buffer_rate.is_finite()
            or self.cost_buffer_rate < 0
            or self.cost_buffer_rate >= 1
        ):
            raise ValueError("cost_buffer_rate must be between zero and one")


@dataclass(frozen=True)
class PositionProtection:
    stop_loss_price: Decimal
    take_profit_price: Decimal
    break_even: BreakEvenPolicy = field(default_factory=BreakEvenPolicy)


@dataclass(frozen=True)
class ProtectionReceipt:
    entry_client_order_id: str
    stop_client_order_id: str
    take_profit_client_order_id: str
    stop_price: Decimal
    take_profit_price: Decimal


@dataclass(frozen=True)
class MarkPrice:
    symbol: str
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True)
class OrderIntent:
    strategy_id: str
    symbol: str
    side: Side
    quantity: Decimal
    reference_price: Decimal
    leverage: int
    client_order_id: str
    market_data_time: datetime
    protection: PositionProtection

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.reference_price


@dataclass(frozen=True)
class Fill:
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    filled_at: datetime

    @classmethod
    def from_intent(cls, intent: OrderIntent) -> "Fill":
        return cls(
            client_order_id=intent.client_order_id,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            price=intent.reference_price,
            filled_at=datetime.now(timezone.utc),
        )
