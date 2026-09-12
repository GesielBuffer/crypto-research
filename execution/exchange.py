from __future__ import annotations

from typing import Protocol

from execution.models import Fill, OrderIntent
from execution.risk import RiskSnapshot


class Exchange(Protocol):
    def snapshot(self) -> RiskSnapshot: ...

    def find_fill(self, intent: OrderIntent) -> Fill | None: ...

    def submit_market(self, intent: OrderIntent) -> Fill: ...
