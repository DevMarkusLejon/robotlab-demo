"""Run an end-to-end intent -> transport -> safety -> UR5e Gazebo demo."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robotlab.intent import HandIntent, IntentGate  # noqa: E402
from robotlab.network import NetworkSimulator  # noqa: E402
from robotlab.pipeline import SharedAutonomyPipeline  # noqa: E402
from robotlab.telemetry import TelemetryRecorder  # noqa: E402
from ur5e_demo import execute_trajectory, trajectory_for_cell  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", type=int, choices=range(9), default=4)
    parser.add_argument("--stable-frames", type=int, default=8)
    parser.add_argument("--settle", type=float, default=1.2)
    parser.add_argument("--latency-ms", type=int, default=80)
    parser.add_argument("--jitter-ms", type=int, default=0)
    parser.add_argument("--drop-rate", type=float, default=0.0)
    parser.add_argument("--deadline-ms", type=int, default=500)
    parser.add_argument("--telemetry", type=Path,
                        default=Path("artifacts/shared-autonomy-events.jsonl"))
    args = parser.parse_args()
    if args.stable_frames < 1 or args.settle <= 0:
        parser.error("--stable-frames must be positive and --settle must be positive")
    if args.latency_ms < 0 or args.jitter_ms < 0 or args.deadline_ms < 0:
        parser.error("latency, jitter and deadline must be nonnegative")
    if not 0 <= args.drop_rate <= 1:
        parser.error("--drop-rate must be in [0, 1]")

    recorder = TelemetryRecorder(args.telemetry)
    pipeline = SharedAutonomyPipeline(
        gate=IntentGate(stable_frames=args.stable_frames),
        network=NetworkSimulator(latency_ms=args.latency_ms,
                                 jitter_ms=args.jitter_ms,
                                 drop_rate=args.drop_rate, seed=0),
        telemetry=recorder,
    )
    row, column = divmod(args.cell, 3)
    x, y = (column + 0.5) / 3, (row + 0.5) / 3
    plan = trajectory_for_cell(args.cell, args.settle)
    recorder.record("demo_started", robot="ur5e_reference", cells=[args.cell],
                    executor="shared_autonomy_pipeline")
    result = None
    for timestamp in range(args.stable_frames):
        result = pipeline.handle_intent(
            HandIntent(x, y, 0.98, timestamp, track_id=1),
            now_ms=timestamp,
            legal_cells={args.cell},
            trajectory=plan,
            deadline_ms=args.deadline_ms,
        )
    if result is None or result.status != "ready":
        recorder.record("demo_aborted", reason=result.reason if result else "no_intent")
        print(f"Demo blocked safely: {result.reason if result else 'no_intent'}", file=sys.stderr)
        return 2
    recorder.record("execution_started", cell=args.cell, stage=result.stage)
    try:
        execute_trajectory(args.cell, plan, args.settle, recorder)
    except (RuntimeError, ValueError) as error:
        recorder.record("demo_aborted", reason=str(error))
        print(f"Demo aborted safely: {error}", file=sys.stderr)
        return 2
    recorder.record("demo_completed", **recorder.summary())
    print(f"End-to-end shared-autonomy demo completed; telemetry written to {args.telemetry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

