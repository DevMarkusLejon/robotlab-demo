"""Evidence metrics computed from RobotLab JSONL event records."""

from __future__ import annotations

from typing import Any, Iterable


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be in [0, 1]")
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    checked = [row for row in rows if row.get("event") == "trajectory_checked"]
    verified = [row for row in rows if row.get("event") == "placement_verified"]
    latencies = [row["latency_ms"] for row in rows if row.get("event") == "transport_delivered" and isinstance(row.get("latency_ms"), (int, float))]
    return {
        "event_count": len(rows),
        "trajectory_checks": len(checked),
        "trajectory_acceptance_rate": (sum(bool(row.get("accepted")) for row in checked) / len(checked)) if checked else None,
        "placement_verification_rate": (len(verified) / len(checked)) if checked else None,
        "transport_latency_p50_ms": percentile(latencies, 0.50),
        "transport_latency_p95_ms": percentile(latencies, 0.95),
    }
