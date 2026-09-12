from __future__ import annotations

from datetime import datetime

from execution.exchange import Exchange
from execution.journal import JsonlOrderJournal
from execution.models import Fill, OrderIntent
from execution.risk import RiskEngine


class TradingService:
    def __init__(
        self,
        exchange: Exchange,
        risk: RiskEngine,
        journal: JsonlOrderJournal | None = None,
    ):
        self.exchange = exchange
        self.risk = risk
        self.journal = journal

    def execute(self, intent: OrderIntent, *, now: datetime | None = None) -> Fill:
        self.risk.validate(intent, self.exchange.snapshot(), now=now)
        if self.journal is not None:
            self.journal.record_intent(intent)
        fill = self.exchange.submit_market(intent)
        if self.journal is not None:
            self.journal.record_fill(fill)
        return fill
