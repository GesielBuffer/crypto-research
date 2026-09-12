from __future__ import annotations

from decimal import Decimal

from execution.models import Fill, OrderIntent, Side
from execution.risk import RiskSnapshot


class PaperExchange:
    """Deterministic, credential-free exchange used before testnet promotion."""

    def __init__(self) -> None:
        self._fills: dict[str, Fill] = {}
        self._positions: dict[str, Decimal] = {}
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

    def activate_kill_switch(self) -> None:
        self._kill_switch = True
