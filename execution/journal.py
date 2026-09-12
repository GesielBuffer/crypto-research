from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from execution.models import Fill, OrderIntent


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
        self._append("intent", asdict(intent))

    def record_fill(self, fill: Fill) -> None:
        self._append("fill", asdict(fill))

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def pending_order_ids(self) -> set[str]:
        intents = set()
        fills = set()
        for record in self.records():
            order_id = record["payload"]["client_order_id"]
            if record["event"] == "intent":
                intents.add(order_id)
            elif record["event"] == "fill":
                fills.add(order_id)
        return intents.difference(fills)
