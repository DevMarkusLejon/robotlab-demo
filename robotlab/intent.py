"""Human-intention gating for a camera-to-robot command pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class HandIntent:
    """One perception result in normalized camera coordinates."""

    x: float
    y: float
    confidence: float
    timestamp_ms: int
    gesture: str = "point"
    track_id: int = 0

    def __post_init__(self) -> None:
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
               for value in (self.x, self.y, self.confidence)):
            raise ValueError("intent coordinates and confidence must be finite numbers")
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("intent coordinates must be normalized to [0, 1]")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if type(self.timestamp_ms) is not int or self.timestamp_ms < 0:
            raise ValueError("timestamp_ms must be a nonnegative integer")
        if type(self.track_id) is not int or self.track_id < 0:
            raise ValueError("track_id must be a nonnegative integer")
        if self.gesture not in {"point", "pinch", "open", "unknown"}:
            raise ValueError("unsupported gesture")


@dataclass(frozen=True)
class IntentDecision:
    status: str
    cell: int | None
    reason: str
    confidence: float
    stable_frames: int


class IntentGate:
    """Reject stale/uncertain gestures and require a stable target before accept."""

    def __init__(self, *, stable_frames: int = 8, min_confidence: float = 0.75,
                 max_age_ms: int = 500, require_gesture: str = "point") -> None:
        if type(stable_frames) is not int or stable_frames < 1:
            raise ValueError("stable_frames must be a positive integer")
        if not 0 < min_confidence <= 1:
            raise ValueError("min_confidence must be in (0, 1]")
        if type(max_age_ms) is not int or max_age_ms < 1:
            raise ValueError("max_age_ms must be a positive integer")
        self.stable_frames = stable_frames
        self.min_confidence = min_confidence
        self.max_age_ms = max_age_ms
        self.require_gesture = require_gesture
        self._last_key: tuple[int, int] | None = None
        self._stable = 0

    @property
    def stable_count(self) -> int:
        return self._stable

    def reset(self) -> None:
        self._last_key = None
        self._stable = 0

    def update(self, intent: HandIntent, *, now_ms: int, legal_cells: set[int] | None = None) -> IntentDecision:
        if type(now_ms) is not int or now_ms < intent.timestamp_ms:
            raise ValueError("now_ms must be an integer at or after intent timestamp")
        cell = self.cell_from_normalized(intent.x, intent.y)
        if now_ms - intent.timestamp_ms > self.max_age_ms:
            self.reset()
            return IntentDecision("rejected", cell, "stale_intent", intent.confidence, 0)
        if intent.gesture != self.require_gesture:
            self.reset()
            return IntentDecision("rejected", cell, "gesture_not_confirmed", intent.confidence, 0)
        if intent.confidence < self.min_confidence:
            self.reset()
            return IntentDecision("rejected", cell, "low_confidence", intent.confidence, 0)
        if cell is None or (legal_cells is not None and cell not in legal_cells):
            self.reset()
            return IntentDecision("rejected", cell, "outside_or_illegal_target", intent.confidence, 0)
        key = (intent.track_id, cell)
        self._stable = self._stable + 1 if key == self._last_key else 1
        self._last_key = key
        status = "accepted" if self._stable >= self.stable_frames else "confirming"
        return IntentDecision(status, cell, "stable_target" if status == "accepted" else "hold_steady", intent.confidence, self._stable)

    @staticmethod
    def cell_from_normalized(x: float, y: float) -> int | None:
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            return None
        col = min(2, int(x * 3))
        row = min(2, int(y * 3))
        return row * 3 + col


def normalized_from_pixel(point: tuple[int, int] | None, *, left: int, top: int, side: int) -> tuple[float, float] | None:
    """Convert a fingertip pixel from the webcam overlay into board coordinates."""
    if point is None:
        return None
    if type(left) is not int or type(top) is not int or type(side) is not int or side < 1:
        raise ValueError("left, top and side must describe a positive pixel square")
    if (not isinstance(point, tuple) or len(point) != 2 or
            any(type(value) is not int for value in point)):
        raise ValueError("point must be a pair of integer pixels or None")
    x, y = point
    if not left <= x < left + side or not top <= y < top + side:
        return None
    return ((x - left + 0.5) / side, (y - top + 0.5) / side)
