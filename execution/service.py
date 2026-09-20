from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from execution.exchange import Exchange
from execution.journal import JsonlOrderJournal
from execution.models import Fill, OrderIntent, ProtectionReceipt, Side, child_order_id
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

    def advance_to_break_even(
        self, intent: OrderIntent, *, mark_price: Decimal
    ) -> ProtectionReceipt | None:
        """Move the stop once to economic break-even after the configured R trigger."""
        policy = intent.protection.break_even
        if not policy.enabled:
            return None
        if not mark_price.is_finite() or mark_price <= 0:
            raise ValueError("mark_price must be positive")

        fill = self.exchange.find_fill(intent)
        if fill is None:
            raise ReconciliationRequired("entry fill is not confirmed by the exchange")
        self._validate_existing_fill(intent, fill)
        if self.exchange.find_emergency_exit(intent) is not None:
            raise PositionProtectionFailed("entry is already closed")
        current = self.exchange.find_protection(intent)
        if current is None:
            raise ReconciliationRequired("position protection is not confirmed")

        break_even_id = child_order_id(intent.client_order_id, "be")
        if current.stop_client_order_id == break_even_id:
            return current

        initial_risk = abs(fill.price - intent.protection.stop_loss_price)
        if fill.side is Side.BUY:
            activation_price = fill.price + policy.activation_r_multiple * initial_risk
            new_stop = fill.price * (Decimal("1") + policy.cost_buffer_rate)
            activated = mark_price >= activation_price
            improves_stop = new_stop > current.stop_price
            safely_behind_market = new_stop < mark_price
            target_not_crossed = mark_price < current.take_profit_price
        else:
            activation_price = fill.price - policy.activation_r_multiple * initial_risk
            new_stop = fill.price * (Decimal("1") - policy.cost_buffer_rate)
            activated = mark_price <= activation_price
            improves_stop = new_stop < current.stop_price
            safely_behind_market = new_stop > mark_price
            target_not_crossed = mark_price > current.take_profit_price

        if not activated:
            return None
        if not target_not_crossed:
            raise ReconciliationRequired(
                "take-profit should have triggered before break-even adjustment"
            )
        if not improves_stop or not safely_behind_market:
            raise ReconciliationRequired(
                "calculated break-even stop is not a safe improvement"
            )

        try:
            adjusted = self.exchange.replace_stop(
                intent, fill, current, new_stop
            )
        except Exception as replacement_error:
            try:
                recovered = self.exchange.find_protection(intent)
            except Exception:
                recovered = None
            if recovered is not None:
                if recovered.stop_client_order_id == break_even_id:
                    if self.journal is not None:
                        self.journal.record_protection_adjustment(recovered)
                    return recovered
                raise ReconciliationRequired(
                    "break-even replacement is unresolved; prior protection remains"
                ) from replacement_error
            try:
                emergency_fill = self.exchange.emergency_close(intent, fill)
                if self.journal is not None:
                    self.journal.record_emergency_exit(emergency_fill)
            except Exception as close_error:
                raise UnprotectedPositionEmergency(
                    "stop replacement and emergency close both failed"
                ) from close_error
            raise PositionProtectionFailed(
                "stop replacement left no confirmed protection; position was closed"
            ) from replacement_error

        if adjusted.stop_client_order_id != break_even_id:
            raise IdempotencyConflict("exchange returned an unexpected break-even stop")
        if self.journal is not None:
            self.journal.record_protection_adjustment(adjusted)
        return adjusted

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
