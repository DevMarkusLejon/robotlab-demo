"""Hardware-independent Cartesian planning for a simulated token-placement demo.

The defaults are fictional example dimensions, not a robot calibration. This
module has no hardware driver and performs no motion, inverse kinematics,
reachability checks, collision checks, or physical emergency-stop function.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from threading import Lock
from typing import Any


Vector3 = tuple[float, float, float]


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _vector(value: object, name: str) -> Vector3:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f"{name} must contain exactly three coordinates in metres")
    return tuple(_number(item, f"{name}[{index}]") for index, item in enumerate(value))  # type: ignore[return-value]


def _cell(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 8:
        raise ValueError("cell must be an integer from 0 to 8")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or value not in ("X", "O"):
        raise ValueError("symbol must be X or O")
    return value


@dataclass(frozen=True)
class CartesianPoint:
    """A position in the geometry's shared coordinate frame, in metres."""

    x_m: float
    y_m: float
    z_m: float

    def __post_init__(self) -> None:
        for name in ("x_m", "y_m", "z_m"):
            object.__setattr__(self, name, _number(getattr(self, name), name))

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class PlacementPlan:
    """Three position waypoints only; tool orientation and pickup are unspecified."""

    cell: int
    symbol: str
    approach: CartesianPoint
    target: CartesianPoint
    retract: CartesianPoint

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoardGeometry:
    """Board corner and orthogonal vectors spanning ONE cell each, in metres.

    Cells are row-major: 0, 1, 2 on the first row, then 3, 4, 5 and 6, 7, 8.
    ``origin_m`` is the outer corner next to cell 0, not that cell's centre.
    Approach/retract follow the right-hand normal ``column_step × row_step``.
    The chosen normal must be checked against any future real installation.

    Example defaults describe 50 mm cells in the XY plane. Each step must be
    between 1 micrometre and 10 metres; these bounds catch degenerate or grossly
    mis-scaled input and do not establish robot-specific feasibility.
    """

    origin_m: Vector3 = (0.0, 0.0, 0.0)
    column_step_m: Vector3 = (0.05, 0.0, 0.0)
    row_step_m: Vector3 = (0.0, 0.05, 0.0)
    clearance_m: float = 0.03

    def __post_init__(self) -> None:
        for name in ("origin_m", "column_step_m", "row_step_m"):
            object.__setattr__(self, name, _vector(getattr(self, name), name))
        lengths = []
        for name in ("column_step_m", "row_step_m"):
            vector = getattr(self, name)
            length = sqrt(sum(component * component for component in vector))
            if not isfinite(length) or not 1e-6 <= length <= 10.0:
                raise ValueError(f"{name} length must be between 0.000001 and 10 metres")
            lengths.append(length)
        dot = sum(a * b for a, b in zip(self.column_step_m, self.row_step_m))
        if abs(dot / lengths[0] / lengths[1]) > 1e-6:
            raise ValueError("column_step_m and row_step_m must be independent and orthogonal")
        clearance = _number(self.clearance_m, "clearance_m")
        if not 0.0 < clearance <= 10.0:
            raise ValueError("clearance_m must be greater than 0 and at most 10 metres")
        object.__setattr__(self, "clearance_m", clearance)

    @property
    def normal(self) -> Vector3:
        """Unit vector in the positive approach direction."""
        a, b = self.column_step_m, self.row_step_m
        cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        length = sqrt(sum(component * component for component in cross))
        return tuple(component / length for component in cross)  # type: ignore[return-value]

    def cell_center(self, cell: int) -> CartesianPoint:
        row, column = divmod(_cell(cell), 3)
        coordinates = tuple(
            origin + (column + 0.5) * column_step + (row + 0.5) * row_step
            for origin, column_step, row_step in zip(self.origin_m, self.column_step_m, self.row_step_m)
        )
        return CartesianPoint(*coordinates)

    def plan_placement(self, cell: int, symbol: str) -> PlacementPlan:
        symbol = _symbol(symbol)
        target = self.cell_center(cell)
        approach = CartesianPoint(*(
            coordinate + self.clearance_m * direction
            for coordinate, direction in zip((target.x_m, target.y_m, target.z_m), self.normal)
        ))
        return PlacementPlan(cell, symbol, approach, target, approach)


class SimulatedRobot:
    """Record proposed waypoints without opening devices or issuing robot commands.

    Stop is a latched software state in this simulator. Reset clears both that
    latch and the simulated history. Command IDs make identical retries
    idempotent within a session; reusing one for a different move is rejected.
    """

    simulation_only = True

    def __init__(self, geometry: BoardGeometry | None = None) -> None:
        if geometry is not None and not isinstance(geometry, BoardGeometry):
            raise ValueError("geometry must be a BoardGeometry")
        self.geometry = geometry if geometry is not None else BoardGeometry()
        self._stopped = False
        self._executed: list[dict[str, Any]] = []
        self._commands: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped

    @property
    def executed(self) -> list[dict[str, Any]]:
        """A detached copy of simulation records; no physical execution is implied."""
        with self._lock:
            return deepcopy(self._executed)

    def place(self, cell: int, symbol: str, command_id: str) -> dict[str, Any]:
        cell, symbol = _cell(cell), _symbol(symbol)
        if not isinstance(command_id, str) or not command_id.strip() or len(command_id) > 128:
            raise ValueError("command_id must be a nonempty string of at most 128 characters")
        with self._lock:
            if self._stopped:
                raise RuntimeError("Simulator is stopped; reset it before placing a token")
            if command_id in self._commands:
                previous = self._commands[command_id]
                if previous["plan"]["cell"] != cell or previous["plan"]["symbol"] != symbol:
                    raise ValueError("command_id has already been used for a different move")
                return deepcopy(previous)
            plan = self.geometry.plan_placement(cell, symbol)
            result = {
                "status": "simulated",
                "simulation_only": True,
                "command_id": command_id,
                "plan": plan.to_dict(),
            }
            self._executed.append(result)
            self._commands[command_id] = result
            return deepcopy(result)

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stopped = True
            return {"status": "stopped", "simulation_only": True, "executed_count": len(self._executed)}

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self._stopped = False
            self._executed.clear()
            self._commands.clear()
            return {"status": "ready", "simulation_only": True, "executed_count": 0}
