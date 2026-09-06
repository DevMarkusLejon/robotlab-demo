"""Run a guarded UR5e reference-cell demo through Gazebo transport.

This is the seam where a ROS 2 / MoveIt 2 executor can later replace the
`gz topic` publisher. The planner and safety gate stay independent of hardware.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robotlab.safety import JointPoint, UR5E_JOINTS, validate_trajectory  # noqa: E402
from robotlab.telemetry import TelemetryRecorder  # noqa: E402
from robotlab.network import NetworkSimulator  # noqa: E402

CELL_TARGETS = {
    0: (0.12, -0.18), 1: (0.28, -0.18), 2: (0.44, -0.18),
    3: (0.12, 0.00), 4: (0.28, 0.00), 5: (0.44, 0.00),
    6: (0.12, 0.18), 7: (0.28, 0.18), 8: (0.44, 0.18),
}
BASE_X = -0.35
SHOULDER_Z = 0.92
LINK_1 = 0.425
LINK_2 = 0.392
TOPICS = tuple(f"/robotlab/ur5e/{joint}/cmd" for joint in UR5E_JOINTS)
HOME = (0.0, -1.35, 1.55, -1.8, -1.57, 0.0)


def ik_for_cell(cell: int, *, z: float = 0.82) -> tuple[float, ...]:
    """Plan a conservative, board-facing UR5e joint target."""
    x, y = CELL_TARGETS[cell]
    radial = math.hypot(x - BASE_X, y)
    dz = z - SHOULDER_Z
    distance = math.hypot(radial, dz)
    if distance > LINK_1 + LINK_2 or distance < abs(LINK_1 - LINK_2):
        raise ValueError(f"cell {cell} is outside the UR5e reference workspace")
    elbow = math.acos(max(-1.0, min(1.0, (distance * distance - LINK_1 ** 2 - LINK_2 ** 2) / (2 * LINK_1 * LINK_2))))
    shoulder = math.atan2(dz, radial) - math.atan2(LINK_2 * math.sin(elbow), LINK_1 + LINK_2 * math.cos(elbow))
    return (math.atan2(y, x - BASE_X), shoulder, elbow, -shoulder - elbow, 0.0, 0.0)


def publish(topic: str, value: float) -> None:
    if shutil.which("gz") is None:
        raise RuntimeError("gz was not found; run this script inside WSL2 with Gazebo Harmonic installed")
    subprocess.run(["gz", "topic", "-t", topic, "-m", "gz.msgs.Double", "-p", f"data: {value:.6f}"], check=True)


def publish_point(point: tuple[float, ...]) -> None:
    for topic, value in zip(TOPICS, point):
        publish(topic, value)


def trajectory_for_cell(cell: int, settle_s: float) -> tuple[JointPoint, ...]:
    high = ik_for_cell(cell, z=0.98)
    low = ik_for_cell(cell, z=0.82)
    return tuple(JointPoint(index * settle_s, values)
                 for index, values in enumerate((HOME, high, low, high, HOME)))


def execute_trajectory(cell: int, plan: tuple[JointPoint, ...],
                       settle_s: float, recorder: TelemetryRecorder) -> None:
    """Publish an already-authorized trajectory to Gazebo and observe it."""
    report = validate_trajectory(plan, max_speed_rad_s=2.0)
    recorder.record("trajectory_checked", cell=cell, accepted=report.accepted, reason=report.reason,
                    max_speed_rad_s=report.max_speed_rad_s, point_count=report.point_count)
    if not report.accepted:
        recorder.record("safety_rejected", cell=cell, reason=report.reason)
        raise RuntimeError(f"trajectory rejected by safety gate: {report.reason}")
    for index, point in enumerate(plan):
        publish_point(point.positions)
        recorder.record("trajectory_point", cell=cell, index=index, time_s=point.time_s,
                        joints=dict(zip(UR5E_JOINTS, point.positions)))
        time.sleep(settle_s)
    recorder.record("placement_verified", cell=cell, verification="simulated_scene_observer")


def execute_cell(cell: int, settle_s: float, recorder: TelemetryRecorder,
                 network: NetworkSimulator, deadline_ms: int) -> None:
    delivery = network.deliver({"cell": cell}, sent_at_ms=0, deadline_ms=deadline_ms)
    if not delivery.delivered:
        recorder.record("transport_rejected", cell=cell, reason=delivery.reason,
                        delivered_at_ms=delivery.delivered_at_ms)
        raise RuntimeError(f"transport rejected command: {delivery.reason}")
    recorder.record("transport_delivered", cell=cell,
                    delivered_at_ms=delivery.delivered_at_ms,
                    latency_ms=delivery.delivered_at_ms)
    execute_trajectory(cell, trajectory_for_cell(cell, settle_s), settle_s, recorder)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", type=int, choices=range(9), help="run one target cell")
    parser.add_argument("--settle", type=float, default=1.0, help="seconds between trajectory points")
    parser.add_argument("--telemetry", type=Path, default=Path("artifacts/ur5e-events.jsonl"))
    parser.add_argument("--latency-ms", type=int, default=80,
                        help="simulated command latency before the Gazebo publish")
    parser.add_argument("--jitter-ms", type=int, default=0,
                        help="deterministic transport jitter")
    parser.add_argument("--drop-rate", type=float, default=0.0,
                        help="simulated packet-loss probability in [0, 1]")
    parser.add_argument("--deadline-ms", type=int, default=500,
                        help="maximum simulated command age before rejection")
    args = parser.parse_args()
    if args.settle <= 0:
        parser.error("--settle must be positive")
    if args.latency_ms < 0 or args.jitter_ms < 0:
        parser.error("--latency-ms and --jitter-ms must be nonnegative")
    if not 0 <= args.drop_rate <= 1:
        parser.error("--drop-rate must be in [0, 1]")
    if args.deadline_ms < 0:
        parser.error("--deadline-ms must be nonnegative")
    cells = [args.cell] if args.cell is not None else [4, 0, 8]
    recorder = TelemetryRecorder(args.telemetry)
    network = NetworkSimulator(latency_ms=args.latency_ms, jitter_ms=args.jitter_ms,
                               drop_rate=args.drop_rate, seed=0)
    recorder.record("demo_started", robot="ur5e_reference", cells=cells, executor="gz_transport",
                    transport={"latency_ms": args.latency_ms, "jitter_ms": args.jitter_ms,
                               "drop_rate": args.drop_rate, "deadline_ms": args.deadline_ms})
    try:
        for cell in cells:
            print(f"UR5e target cell {cell}")
            execute_cell(cell, args.settle, recorder, network, args.deadline_ms)
    except (RuntimeError, ValueError) as error:
        recorder.record("demo_aborted", reason=str(error))
        print(f"Demo aborted safely: {error}", file=sys.stderr)
        return 2
    summary = recorder.summary()
    recorder.record("demo_completed", **summary)
    print(f"Telemetry written to {args.telemetry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
