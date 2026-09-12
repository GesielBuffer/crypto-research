from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from execution.models import Fill, OrderIntent, Side


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
