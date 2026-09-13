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


class PositionProtectionFailed(RuntimeError):
    pass


class UnprotectedPositionEmergency(RuntimeError):
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
            emergency_exit = self.exchange.find_emergency_exit(intent)
            if emergency_exit is not None:
                if self.journal is not None:
                    self.journal.record_emergency_exit(emergency_exit)
                raise PositionProtectionFailed(
                    "entry was already closed after a protection failure"
                )
            self._ensure_protected(intent, remote_fill)
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
        self._ensure_protected(intent, fill)
        return fill

    def _ensure_protected(self, intent: OrderIntent, fill: Fill) -> None:
        try:
            self.risk.validate_fill_protection(intent, fill)
            protection = self.exchange.find_protection(intent)
            if protection is None:
                protection = self.exchange.submit_protection(intent, fill)
            if protection.entry_client_order_id != intent.client_order_id:
                raise IdempotencyConflict("protection belongs to a different entry")
        except Exception as protection_error:
            try:
                emergency_fill = self.exchange.emergency_close(intent, fill)
                if self.journal is not None:
                    self.journal.record_emergency_exit(emergency_fill)
            except Exception as close_error:
                raise UnprotectedPositionEmergency(
                    "protection and emergency close both failed; manual intervention required"
                ) from close_error
            raise PositionProtectionFailed(
                "protection failed; position was closed immediately"
            ) from protection_error
        if self.journal is not None:
            self.journal.record_protection(protection)

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
