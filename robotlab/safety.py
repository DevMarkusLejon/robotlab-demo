"""Safety gates for planned UR5e joint trajectories."""

from __future__ import annotations

from dataclasses import dataclass
import math


UR5E_JOINTS = ("shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint",
               "wrist_1_joint", "wrist_2_joint", "wrist_3_joint")
UR5E_LIMITS = ((-2 * math.pi, 2 * math.pi), (-2.5, 0.2), (-2.8, 2.8),
               (-3.2, 0.2), (-2 * math.pi, 2 * math.pi), (-2 * math.pi, 2 * math.pi))


@dataclass(frozen=True)
class JointPoint:
    time_s: float
    positions: tuple[float, ...]


@dataclass(frozen=True)
class SafetyReport:
    accepted: bool
    reason: str
    max_speed_rad_s: float
    point_count: int


def validate_trajectory(points: tuple[JointPoint, ...], *, max_speed_rad_s: float = 1.5) -> SafetyReport:
    """Validate finite values, limits, monotonic time and speed before publishing."""
    if not points:
        return SafetyReport(False, "empty_trajectory", 0.0, 0)
    if not 0 < max_speed_rad_s <= 10 or not math.isfinite(max_speed_rad_s):
        raise ValueError("max_speed_rad_s must be finite and in (0, 10]")
    previous: JointPoint | None = None
    observed_speed = 0.0
    for point in points:
        if len(point.positions) != len(UR5E_JOINTS) or not math.isfinite(point.time_s) or point.time_s < 0:
            return SafetyReport(False, "malformed_point", observed_speed, len(points))
        if previous is not None:
            dt = point.time_s - previous.time_s
            if dt <= 0:
                return SafetyReport(False, "non_monotonic_time", observed_speed, len(points))
            for index, (current, prior) in enumerate(zip(point.positions, previous.positions)):
                if not math.isfinite(current):
                    return SafetyReport(False, "nonfinite_joint", observed_speed, len(points))
                low, high = UR5E_LIMITS[index]
                if not low <= current <= high:
                    return SafetyReport(False, f"joint_limit:{UR5E_JOINTS[index]}", observed_speed, len(points))
                observed_speed = max(observed_speed, abs(current - prior) / dt)
        else:
            for index, current in enumerate(point.positions):
                if not math.isfinite(current):
                    return SafetyReport(False, "nonfinite_joint", observed_speed, len(points))
                low, high = UR5E_LIMITS[index]
                if not low <= current <= high:
                    return SafetyReport(False, f"joint_limit:{UR5E_JOINTS[index]}", observed_speed, len(points))
        previous = point
    if observed_speed > max_speed_rad_s:
        return SafetyReport(False, "speed_limit", observed_speed, len(points))
    return SafetyReport(True, "accepted", observed_speed, len(points))
