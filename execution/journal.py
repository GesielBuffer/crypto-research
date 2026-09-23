from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from execution.models import (
    BreakEvenPolicy,
    Fill,
    OrderIntent,
    PositionProtection,
    ProtectionReceipt,
    Side,
)


def _json_value(value):
    if isinstance(value, (Decimal, datetime)):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"unsupported journal value: {type(value).__name__}")


class JsonlOrderJournal:
    """Append-only order journal used to detect incomplete submissions."""

    def __init__(self, path: Path):
        self.path = path

    def _append(self, event: str, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps(
            {"event": event, "payload": payload},
            default=_json_value,
            sort_keys=True,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def record_intent(self, intent: OrderIntent) -> None:
        if intent.client_order_id not in self.intent_ids():
            self._append("intent", asdict(intent))

    def record_fill(self, fill: Fill) -> None:
        if self.fill_for(fill.client_order_id) is None:
            self._append("fill", asdict(fill))

    def record_protection(self, receipt: ProtectionReceipt) -> None:
        if receipt.entry_client_order_id not in self.protected_entry_ids():
            self._append("protection", asdict(receipt))

    def record_protection_adjustment(self, receipt: ProtectionReceipt) -> None:
        if receipt.stop_client_order_id not in self.adjusted_stop_ids():
            self._append("protection_adjustment", asdict(receipt))

    def record_emergency_exit(self, fill: Fill) -> None:
        if fill.client_order_id not in self.emergency_exit_ids():
            self._append("emergency_exit", asdict(fill))

    def record_position_closed(self, entry_client_order_id: str) -> None:
        if entry_client_order_id not in self.closed_entry_ids():
            self._append(
                "position_closed",
                {"entry_client_order_id": entry_client_order_id},
            )

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def pending_order_ids(self) -> set[str]:
        return self.intent_ids().difference(self.fill_ids())

    def intent_ids(self) -> set[str]:
        return {
            record["payload"]["client_order_id"]
            for record in self.records()
            if record["event"] == "intent"
        }

    def fill_ids(self) -> set[str]:
        return {
            record["payload"]["client_order_id"]
            for record in self.records()
            if record["event"] == "fill"
        }

    def protected_entry_ids(self) -> set[str]:
        return {
            record["payload"]["entry_client_order_id"]
            for record in self.records()
            if record["event"] == "protection"
        }

    def emergency_exit_ids(self) -> set[str]:
        return {
            record["payload"]["client_order_id"]
            for record in self.records()
            if record["event"] == "emergency_exit"
        }

    def adjusted_stop_ids(self) -> set[str]:
        return {
            record["payload"]["stop_client_order_id"]
            for record in self.records()
            if record["event"] == "protection_adjustment"
        }

    def closed_entry_ids(self) -> set[str]:
        return {
            record["payload"]["entry_client_order_id"]
            for record in self.records()
            if record["event"] == "position_closed"
        }

    def fill_for(self, client_order_id: str) -> Fill | None:
        for record in self.records():
            payload = record["payload"]
            if record["event"] != "fill" or payload["client_order_id"] != client_order_id:
                continue
            return Fill(
                client_order_id=payload["client_order_id"],
                symbol=payload["symbol"],
                side=Side(payload["side"]),
                quantity=Decimal(payload["quantity"]),
                price=Decimal(payload["price"]),
                filled_at=datetime.fromisoformat(payload["filled_at"]),
            )
        return None

    def intent_for(self, client_order_id: str) -> OrderIntent | None:
        for record in self.records():
            payload = record["payload"]
            if (
                record["event"] != "intent"
                or payload["client_order_id"] != client_order_id
            ):
                continue
            protection_payload = payload["protection"]
            break_even_payload = protection_payload.get("break_even", {})
            return OrderIntent(
                strategy_id=payload["strategy_id"],
                symbol=payload["symbol"],
                side=Side(payload["side"]),
                quantity=Decimal(payload["quantity"]),
                reference_price=Decimal(payload["reference_price"]),
                leverage=int(payload["leverage"]),
                client_order_id=payload["client_order_id"],
                market_data_time=datetime.fromisoformat(payload["market_data_time"]),
                protection=PositionProtection(
                    stop_loss_price=Decimal(protection_payload["stop_loss_price"]),
                    take_profit_price=Decimal(
                        protection_payload["take_profit_price"]
                    ),
                    break_even=BreakEvenPolicy(
                        enabled=bool(break_even_payload.get("enabled", False)),
                        activation_r_multiple=Decimal(
                            break_even_payload.get("activation_r_multiple", "1")
                        ),
                        cost_buffer_rate=Decimal(
                            break_even_payload.get("cost_buffer_rate", "0")
                        ),
                    ),
                ),
            )
        return None

    def intents(self) -> list[OrderIntent]:
        values = []
        for client_order_id in sorted(self.intent_ids()):
            intent = self.intent_for(client_order_id)
            if intent is not None:
                values.append(intent)
        return values
