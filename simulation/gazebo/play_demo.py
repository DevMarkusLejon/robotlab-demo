"""Drive the RobotLab Gazebo arm to board cells through gz topic."""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import time
from pathlib import Path

BOARD = {
    0: (0.18, -0.26), 1: (0.40, -0.26), 2: (0.62, -0.26),
    3: (0.18, 0.00), 4: (0.40, 0.00), 5: (0.62, 0.00),
    6: (0.18, 0.26), 7: (0.40, 0.26), 8: (0.62, 0.26),
}
BASE_X = 0.0
SHOULDER_Z = 0.34
LINK_1 = 0.42
LINK_2 = 0.32


def joint_angles(cell: int, z: float = 0.16) -> tuple[float, float, float]:
    """Return base, shoulder, elbow angles for a board cell."""
    x, y = BOARD[cell]
    radial = math.hypot(x - BASE_X, y)
    dz = z - SHOULDER_Z
    distance = math.hypot(radial, dz)
    if distance > LINK_1 + LINK_2 or distance < abs(LINK_1 - LINK_2):
        raise ValueError(f"cell {cell} is outside arm reach")
    elbow = math.acos((distance * distance - LINK_1 * LINK_1 - LINK_2 * LINK_2) / (2 * LINK_1 * LINK_2))
    shoulder = math.atan2(dz, radial) - math.atan2(LINK_2 * math.sin(elbow), LINK_1 + LINK_2 * math.cos(elbow))
    return math.atan2(y, x - BASE_X), shoulder, -elbow


def publish(topic: str, value: float) -> None:
    if shutil.which("gz") is None:
        raise RuntimeError("gz was not found. Run this from Gazebo Harmonic or WSL2.")
    subprocess.run(["gz", "topic", "-t", topic, "-m", "gz.msgs.Double", "-p", f"data: {value:.6f}"], check=True)


def move(cell: int, settle: float = 1.0) -> None:
    base, shoulder, elbow = joint_angles(cell)
    # Approach high, descend into the cell, then retract. This is intentionally
    # slow and inspectable so it can become a real trajectory later.
    high = joint_angles(cell, z=0.29)
    for values in (high, (base, shoulder, elbow)):
        for topic, value in zip(("/robotlab/arm/base/cmd", "/robotlab/arm/shoulder/cmd", "/robotlab/arm/elbow/cmd"), values):
            publish(topic, value)
        time.sleep(settle)
    for topic, value in zip(("/robotlab/arm/base/cmd", "/robotlab/arm/shoulder/cmd", "/robotlab/arm/elbow/cmd"), high):
        publish(topic, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", type=int, choices=range(9), help="move once to cell 0-8")
    parser.add_argument("--settle", type=float, default=1.0)
    args = parser.parse_args()
    cells = [args.cell] if args.cell is not None else [0, 4, 8, 2, 6]
    for cell in cells:
        print(f"Moving to cell {cell}...")
        move(cell, args.settle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
