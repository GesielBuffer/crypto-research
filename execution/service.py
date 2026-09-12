from __future__ import annotations

from datetime import datetime

from execution.exchange import Exchange
from execution.journal import JsonlOrderJournal
from execution.models import Fill, OrderIntent
from execution.risk import RiskEngine


class ReconciliationRequired(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


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
        remote_fill = self.exchange.find_fill(intent)
        if remote_fill is not None:
            self._validate_existing_fill(intent, remote_fill)
            if self.journal is not None:
                self.journal.record_fill(remote_fill)
            return remote_fill
        if self.journal is not None:
            recorded_fill = self.journal.fill_for(intent.client_order_id)
            if recorded_fill is not None:
                raise ReconciliationRequired(
                    "journal contains a fill that the exchange cannot confirm"
                )
            if intent.client_order_id in self.journal.pending_order_ids():
                raise ReconciliationRequired(
                    "previous submission is unresolved; reconcile before retrying"
                )
        self.risk.validate(intent, self.exchange.snapshot(), now=now)
        if self.journal is not None:
            self.journal.record_intent(intent)
        fill = self.exchange.submit_market(intent)
        if self.journal is not None:
            self.journal.record_fill(fill)
        return fill

    @staticmethod
    def _validate_existing_fill(intent: OrderIntent, fill: Fill) -> None:
        if (
            fill.symbol != intent.symbol
            or fill.side != intent.side
            or fill.quantity != intent.quantity
        ):
            raise IdempotencyConflict(
                "client_order_id is already bound to a different order"
            )
