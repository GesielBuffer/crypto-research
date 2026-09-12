from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


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
