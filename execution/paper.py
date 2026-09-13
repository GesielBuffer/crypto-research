from __future__ import annotations

from decimal import Decimal

from execution.models import (
    Fill,
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

    def snapshot(self) -> RiskSnapshot:
        return RiskSnapshot(
            open_symbols=frozenset(
                symbol for symbol, quantity in self._positions.items() if quantity != 0
            ),
            realized_pnl_today=self._realized_pnl_today,
            kill_switch=self._kill_switch,
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
