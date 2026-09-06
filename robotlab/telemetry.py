"""Small dependency-free JSONL recorder for demo evidence and later metrics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .metrics import summarize_events


class TelemetryRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        json.dumps(payload, allow_nan=False)
        self.events.append(payload)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, allow_nan=False, sort_keys=True) + "\n")
        return payload

    def summary(self) -> dict[str, Any]:
        events = [item["event"] for item in self.events]
        summary = {"event_count": len(events), "events": events,
                   "accepted_intents": sum(item == "intent_accepted" for item in events),
                   "safety_rejections": sum(item == "safety_rejected" for item in events)}
        summary.update(summarize_events(self.events))
        return summary
