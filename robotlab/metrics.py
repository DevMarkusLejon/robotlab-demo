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
    rows = [row for row in events if row.get('source') != 'offline_fixture']
    checked = [row for row in rows if row.get("event") == "trajectory_checked"]
    # Legacy demos emitted this name without a sensor. Do not count those
    # placeholders (or a bare event name) as evidence of object placement.
    observed = [row for row in rows if row.get("event") == "placement_observed"
                and row.get("verification") == "camera"
                and isinstance(row.get("frame_id"), str) and row["frame_id"]]
    verified = [row for row in observed if row.get("accepted") is True]
    latencies = [row["latency_ms"] for row in rows if row.get("event") == "transport_delivered" and isinstance(row.get("latency_ms"), (int, float))]
    attempts = {row['attempt_id']: row for row in rows
                if row.get('event') == 'pick_place_started' and row.get('attempt_id')}
    camera_attempts = {row.get('attempt_id') for row in verified
                       if row.get('source') in ('gazebo_rendered_camera', 'physical_board_camera') and row.get('confirming_frames', 0) >= 3}
    completions = {row['attempt_id']: row for row in rows
                   if row.get('event') == 'pick_place_completed' and row.get('attempt_id') in attempts
                   and row.get('attempt_id') in camera_attempts}
    durations = [row['duration_s'] for row in completions.values() if 'duration_s' in row]
    per_cell = {}
    for cell in range(9):
        ids = {key for key, row in attempts.items() if row.get('cell') == cell}
        successes = len(ids & completions.keys())
        per_cell[str(cell)] = {'attempts': len(ids), 'verified': successes,
                              'success_rate': successes / len(ids) if ids else None}
    return {
        'placement_attempts': len(attempts),
        'camera_verified_completions': len(completions),
        'placement_attempt_success_rate': len(completions) / len(attempts) if attempts else None,
        'placement_duration_p50_s': percentile(durations, .5),
        'placement_duration_p95_s': percentile(durations, .95),
        'per_cell': per_cell,
        "event_count": len(rows),
        "trajectory_checks": len(checked),
        "trajectory_acceptance_rate": (sum(bool(row.get("accepted")) for row in checked) / len(checked)) if checked else None,
        "placement_observations": len(observed),
        "placement_verification_rate": (len(verified) / len(observed)) if observed else None,
        "transport_latency_p50_ms": percentile(latencies, 0.50),
        "transport_latency_p95_ms": percentile(latencies, 0.95),
    }


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Summarize scoped simulation placement evidence')
    parser.add_argument('logs', nargs='+', type=Path)
    args = parser.parse_args()
    events = [json.loads(line) for path in args.logs
              for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    print(json.dumps(summarize_events(events), ensure_ascii=False, indent=2))
