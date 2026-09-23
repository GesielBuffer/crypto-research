from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from execution.models import Fill, MarkPrice, OrderIntent, ProtectionReceipt
from execution.risk import RiskSnapshot


class Exchange(Protocol):
    def snapshot(self) -> RiskSnapshot: ...

    def position_quantity(self, symbol: str) -> Decimal: ...

    def get_mark_price(self, symbol: str) -> MarkPrice: ...

    def find_fill(self, intent: OrderIntent) -> Fill | None: ...

    def submit_market(self, intent: OrderIntent) -> Fill: ...

    def find_protection(self, intent: OrderIntent) -> ProtectionReceipt | None: ...

    def open_protection_ids(self, intent: OrderIntent) -> frozenset[str]: ...

    def cancel_protection(self, intent: OrderIntent) -> None: ...

    def submit_protection(
        self, intent: OrderIntent, entry_fill: Fill
    ) -> ProtectionReceipt: ...

    def replace_stop(
        self,
        intent: OrderIntent,
        entry_fill: Fill,
        current: ProtectionReceipt,
        new_stop_price: Decimal,
    ) -> ProtectionReceipt: ...

    def emergency_close(self, intent: OrderIntent, entry_fill: Fill) -> Fill: ...

    def find_emergency_exit(self, intent: OrderIntent) -> Fill | None: ...
