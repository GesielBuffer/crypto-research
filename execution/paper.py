from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from execution.models import (
    Fill,
    MarkPrice,
    OrderIntent,
    ProtectionReceipt,
    Side,
    child_order_id,
)
from execution.risk import RiskSnapshot


class PaperExchange:
    """Deterministic, credential-free exchange used before testnet promotion."""

    def __init__(self) -> None:
        self._fills: dict[str, Fill] = {}
        self._positions: dict[str, Decimal] = {}
        self._protections: dict[str, ProtectionReceipt] = {}
        self._realized_pnl_today = Decimal("0")
        self._kill_switch = False
        self._mark_prices: dict[str, MarkPrice] = {}

    def snapshot(self) -> RiskSnapshot:
        return RiskSnapshot(
            open_symbols=frozenset(
                symbol for symbol, quantity in self._positions.items() if quantity != 0
            ),
            realized_pnl_today=self._realized_pnl_today,
            kill_switch=self._kill_switch,
        )

    def position_quantity(self, symbol: str) -> Decimal:
        return self._positions.get(symbol, Decimal("0"))

    def get_mark_price(self, symbol: str) -> MarkPrice:
        quote = self._mark_prices.get(symbol)
        if quote is None:
            raise RuntimeError(f"paper mark price is not set for {symbol}")
        return quote

    def set_mark_price(
        self,
        symbol: str,
        price: Decimal,
        *,
        observed_at: datetime | None = None,
    ) -> None:
        self._mark_prices[symbol] = MarkPrice(
            symbol=symbol,
            price=price,
            observed_at=observed_at or datetime.now(timezone.utc),
        )

    def submit_market(self, intent: OrderIntent) -> Fill:
        existing = self._fills.get(intent.client_order_id)
        if existing is not None:
            return existing
        fill = Fill.from_intent(intent)
        direction = Decimal("1") if intent.side is Side.BUY else Decimal("-1")
        self._positions[intent.symbol] = (
            self._positions.get(intent.symbol, Decimal("0"))
            + direction * intent.quantity
        )
        self._fills[intent.client_order_id] = fill
        return fill

    def find_fill(self, intent: OrderIntent) -> Fill | None:
        return self._fills.get(intent.client_order_id)

    def find_protection(self, intent: OrderIntent) -> ProtectionReceipt | None:
        return self._protections.get(intent.client_order_id)

    def open_protection_ids(self, intent: OrderIntent) -> frozenset[str]:
        receipt = self.find_protection(intent)
        if receipt is None:
            return frozenset()
        return frozenset(
            {receipt.stop_client_order_id, receipt.take_profit_client_order_id}
        )

    def cancel_protection(self, intent: OrderIntent) -> None:
        self._protections.pop(intent.client_order_id, None)

    def submit_protection(
        self, intent: OrderIntent, entry_fill: Fill
    ) -> ProtectionReceipt:
        existing = self.find_protection(intent)
        if existing is not None:
            return existing
        receipt = ProtectionReceipt(
            entry_client_order_id=intent.client_order_id,
            stop_client_order_id=child_order_id(intent.client_order_id, "sl"),
            take_profit_client_order_id=child_order_id(intent.client_order_id, "tp"),
            stop_price=intent.protection.stop_loss_price,
            take_profit_price=intent.protection.take_profit_price,
        )
        self._protections[intent.client_order_id] = receipt
        return receipt

    def replace_stop(
        self,
        intent: OrderIntent,
        entry_fill: Fill,
        current: ProtectionReceipt,
        new_stop_price: Decimal,
    ) -> ProtectionReceipt:
        existing = self.find_protection(intent)
        if existing is None or existing != current:
            raise RuntimeError("paper protection changed before stop replacement")
        receipt = ProtectionReceipt(
            entry_client_order_id=intent.client_order_id,
            stop_client_order_id=child_order_id(intent.client_order_id, "be"),
            take_profit_client_order_id=current.take_profit_client_order_id,
            stop_price=new_stop_price,
            take_profit_price=current.take_profit_price,
        )
        self._protections[intent.client_order_id] = receipt
        return receipt

    def emergency_close(self, intent: OrderIntent, entry_fill: Fill) -> Fill:
        exit_id = child_order_id(intent.client_order_id, "exit")
        existing = self._fills.get(exit_id)
        if existing is not None:
            return existing
        fill = Fill(
            client_order_id=exit_id,
            symbol=entry_fill.symbol,
            side=entry_fill.side.opposite,
            quantity=entry_fill.quantity,
            price=entry_fill.price,
            filled_at=entry_fill.filled_at,
        )
        direction = Decimal("1") if fill.side is Side.BUY else Decimal("-1")
        self._positions[fill.symbol] = (
            self._positions.get(fill.symbol, Decimal("0"))
            + direction * fill.quantity
        )
        self._protections.pop(intent.client_order_id, None)
        self._fills[exit_id] = fill
        return fill

    def find_emergency_exit(self, intent: OrderIntent) -> Fill | None:
        return self._fills.get(child_order_id(intent.client_order_id, "exit"))

    def activate_kill_switch(self) -> None:
        self._kill_switch = True

    def simulate_protection_fill(self, intent: OrderIntent) -> None:
        """Settle a paper position as if an exchange-side trigger had filled."""
        self._positions[intent.symbol] = Decimal("0")
        self._protections.pop(intent.client_order_id, None)
