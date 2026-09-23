from __future__ import annotations

from dataclasses import asdict, dataclass

from execution.journal import JsonlOrderJournal
from execution.models import OrderIntent, child_order_id
from execution.service import (
    PositionAlreadyClosed,
    PositionProtectionFailed,
    ReconciliationRequired,
    TradingService,
)


@dataclass(frozen=True)
class RecoveryItem:
    entry_client_order_id: str
    symbol: str
    status: str
    detail: str


@dataclass(frozen=True)
class RecoveryReport:
    items: tuple[RecoveryItem, ...]

    @property
    def blockers(self) -> tuple[RecoveryItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.status in {"unresolved", "divergence", "attention_required"}
        )

    @property
    def ready(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "blockers": len(self.blockers),
            "items": [asdict(item) for item in self.items],
        }


class JournalRecovery:
    """Reconcile journaled entries without ever submitting a new entry order."""

    def __init__(self, service: TradingService, journal: JsonlOrderJournal):
        if service.journal is not journal:
            raise ValueError("service and recovery must share the same journal")
        self.service = service
        self.journal = journal

    def recover(self) -> RecoveryReport:
        items = tuple(self._recover_intent(intent) for intent in self.journal.intents())
        return RecoveryReport(items)

    def _recover_intent(self, intent: OrderIntent) -> RecoveryItem:
        entry_id = intent.client_order_id
        if entry_id in self.journal.closed_entry_ids():
            return RecoveryItem(entry_id, intent.symbol, "closed", "already recorded")
        emergency_id = child_order_id(entry_id, "exit")
        if emergency_id in self.journal.emergency_exit_ids():
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "emergency_closed",
                "emergency exit already recorded",
            )

        local_fill = self.journal.fill_for(entry_id)
        try:
            remote_fill = self.service.exchange.find_fill(intent)
        except Exception as exc:
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "attention_required",
                f"entry lookup failed: {type(exc).__name__}",
            )
        if remote_fill is None:
            if local_fill is not None:
                return RecoveryItem(
                    entry_id,
                    intent.symbol,
                    "divergence",
                    "journal fill is absent from exchange",
                )
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "unresolved",
                "intent is not confirmed or rejected by exchange",
            )

        try:
            self.service.execute(intent)
        except PositionAlreadyClosed as exc:
            return RecoveryItem(entry_id, intent.symbol, "closed", str(exc))
        except PositionProtectionFailed as exc:
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "emergency_closed",
                str(exc),
            )
        except ReconciliationRequired as exc:
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "attention_required",
                str(exc),
            )
        except Exception as exc:
            return RecoveryItem(
                entry_id,
                intent.symbol,
                "attention_required",
                f"recovery failed: {type(exc).__name__}: {exc}",
            )
        return RecoveryItem(
            entry_id,
            intent.symbol,
            "protected",
            "entry, position and protection reconciled",
        )
