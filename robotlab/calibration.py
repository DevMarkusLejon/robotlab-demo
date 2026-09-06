"""Dependency-free planar camera calibration for the RobotLab board."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable


Pixel = tuple[float, float]


def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    """Solve a small dense system with pivoting, raising on a degenerate setup."""
    size = len(values)
    augmented = [row[:] + [value] for row, value in zip(matrix, values)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("calibration points are degenerate")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [left - factor * right
                                  for left, right in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


def _point(value: object, name: str) -> Pixel:
    if (not isinstance(value, (tuple, list)) or len(value) != 2 or
            any(isinstance(item, bool) or not isinstance(item, (int, float)) or
                not math.isfinite(float(item)) for item in value)):
        raise ValueError(f"{name} must be a finite 2D point")
    return float(value[0]), float(value[1])


@dataclass(frozen=True)
class BoardCalibration:
    """Map image points from four board corners to normalized board coordinates.

    Corner order is top-left, top-right, bottom-right, bottom-left as seen by
    the camera. The destination square is ``[0, 1] × [0, 1]``.
    """

    corners_px: tuple[Pixel, Pixel, Pixel, Pixel]

    @classmethod
    def from_json(cls, path: str | Path) -> "BoardCalibration":
        """Load a four-corner calibration captured by a setup tool."""
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            corners = tuple(tuple(point) for point in payload["corners_px"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("calibration file must contain corners_px with four points") from exc
        return cls(corners)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        if not isinstance(self.corners_px, tuple) or len(self.corners_px) != 4:
            raise ValueError("corners_px must contain four corners")
        corners = tuple(_point(point, f"corners_px[{index}]")
                        for index, point in enumerate(self.corners_px))
        if len(set(corners)) != 4:
            raise ValueError("calibration corners must be distinct")
        object.__setattr__(self, "corners_px", corners)
        # A homography is defined by eight linear equations and h33 = 1.
        matrix: list[list[float]] = []
        values: list[float] = []
        for (x, y), (u, v) in zip(corners, ((0.0, 0.0), (1.0, 0.0),
                                           (1.0, 1.0), (0.0, 1.0))):
            matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
            values.append(u)
            matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
            values.append(v)
        object.__setattr__(self, "_homography", tuple(_solve(matrix, values) + [1.0]))

    def normalized(self, point: Iterable[float]) -> Pixel | None:
        """Return normalized board coordinates, or ``None`` outside the board."""
        x, y = _point(tuple(point), "point")
        h = self._homography
        denominator = h[6] * x + h[7] * y + h[8]
        if abs(denominator) < 1e-12:
            return None
        u = (h[0] * x + h[1] * y + h[2]) / denominator
        v = (h[3] * x + h[4] * y + h[5]) / denominator
        if not 0.0 <= u <= 1.0 or not 0.0 <= v <= 1.0:
            return None
        return u, v

    def cell(self, point: Iterable[float]) -> int | None:
        normalized = self.normalized(point)
        if normalized is None:
            return None
        u, v = normalized
        return min(2, int(u * 3)) + 3 * min(2, int(v * 3))
