"""Calibrated red/blue token observation and evidence-based placement checks.

This observer targets matte round red (X) and blue (O) demo tokens. It is not
a general object detector. Calibration and an unobstructed camera are required.
"""
from dataclasses import dataclass
import math

from .calibration import BoardCalibration


@dataclass(frozen=True)
class BoardObservation:
    frame_id: str
    timestamp_ms: int
    cells: tuple[str | None, ...]
    valid: bool = True
    reason: str = 'observed'


def observe_tokens(frame, calibration: BoardCalibration, *, frame_id, timestamp_ms,
                   occluded=False):
    import cv2
    import numpy as np
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('frame must be a BGR image')
    if occluded:
        return BoardObservation(frame_id, timestamp_ms, (None,) * 9, False, 'occluded')
    height, width = frame.shape[:2]
    if any(not (0 <= x < width and 0 <= y < height) for x, y in calibration.corners_px):
        return BoardObservation(frame_id, timestamp_ms, (None,) * 9, False, 'board_outside_image')
    transform = cv2.getPerspectiveTransform(np.float32(calibration.corners_px),
        np.float32(((0, 0), (599, 0), (599, 599), (0, 599))))
    board = cv2.warpPerspective(frame, transform, (600, 600))
    hsv = cv2.cvtColor(board, cv2.COLOR_BGR2HSV)
    masks = {
        'X': cv2.inRange(hsv, (0, 100, 70), (10, 255, 255)) |
             cv2.inRange(hsv, (170, 100, 70), (179, 255, 255)),
        'O': cv2.inRange(hsv, (100, 100, 70), (130, 255, 255)),
    }
    cells = [None] * 9
    ambiguous = False
    for symbol, mask in masks.items():
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 80:  # Ignore isolated pixel noise after rectification.
                continue
            x, y, w, h = cv2.boundingRect(contour)
            perimeter = cv2.arcLength(contour, True)
            circularity = 4 * math.pi * area / perimeter ** 2 if perimeter else 0
            # Token must fit inside one cell and have plausible circular size.
            if not 250 <= area <= 8000 or circularity < 0.65 or (
                x // 200 != (x + w - 1) // 200 or y // 200 != (y + h - 1) // 200):
                ambiguous = True
                continue
            cell = (y + h // 2) // 200 * 3 + (x + w // 2) // 200
            if cells[cell] is not None:
                ambiguous = True
            cells[cell] = symbol
    return BoardObservation(frame_id, timestamp_ms, tuple(cells), not ambiguous,
                            'ambiguous_tokens' if ambiguous else 'observed')


class PlacementVerifier:
    """Require a baseline and several fresh frames showing exactly one change."""
    def __init__(self, baseline, *, cell, symbol, commanded_at_ms, stable_frames=3):
        if not baseline.valid or len(baseline.cells) != 9:
            raise ValueError('baseline must be a valid nine-cell observation')
        if type(cell) is not int or not 0 <= cell < 9 or baseline.cells[cell] is not None:
            raise ValueError('target must be an empty cell')
        if symbol not in ('X', 'O') or type(stable_frames) is not int or stable_frames < 2:
            raise ValueError('symbol and stable_frames are invalid')
        if commanded_at_ms < baseline.timestamp_ms or commanded_at_ms - baseline.timestamp_ms > 500:
            raise ValueError('baseline must be fresh at command time')
        self.expected = list(baseline.cells)
        self.expected[cell] = symbol
        self.expected = tuple(self.expected)
        self.commanded_at_ms = commanded_at_ms
        self.last_time = baseline.timestamp_ms
        self.last_frame = baseline.frame_id
        self.required = stable_frames
        self.stable = 0
        self.done = False

    def update(self, observation, *, now_ms):
        if self.done:
            return 'already_verified'
        if (not observation.valid or len(observation.cells) != 9 or
            observation.timestamp_ms <= self.commanded_at_ms or
            observation.timestamp_ms <= self.last_time or
            observation.frame_id == self.last_frame or
            not 0 <= now_ms - observation.timestamp_ms <= 500):
            self.stable = 0
            return 'invalid_or_stale_observation'
        self.last_time = observation.timestamp_ms
        self.last_frame = observation.frame_id
        if observation.cells != self.expected:
            self.stable = 0
            return 'board_change_mismatch'
        self.stable += 1
        self.done = self.stable >= self.required
        return 'verified' if self.done else 'confirming'
