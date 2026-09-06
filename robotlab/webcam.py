"""Play the provisional game through a webcam, with the user as the robot arm.

The camera only selects a board cell. The placement itself remains simulated;
no camera frame is sent anywhere and no physical robot driver is loaded.
OpenCV is imported lazily so the rest of the package stays dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .calibration import BoardCalibration
from .intent import HandIntent, IntentGate, normalized_from_pixel
from .session import Session, make_command


@dataclass(frozen=True)
class BoardRect:
    """Square board overlay in image pixels (left, top, side)."""

    left: int
    top: int
    side: int

    def __post_init__(self) -> None:
        if any(type(value) is not int for value in (self.left, self.top, self.side)):
            raise ValueError("board rectangle coordinates must be integers")
        if self.side < 3:
            raise ValueError("board side must be at least 3 pixels")


@dataclass(frozen=True)
class HandObservation:
    """Per-frame hand result used by the intent gate."""

    fingertip: tuple[int, int]
    confidence: float
    gesture: str = "point"
    track_id: int = 0

    def __post_init__(self) -> None:
        if (not isinstance(self.fingertip, tuple) or len(self.fingertip) != 2 or
                any(type(value) is not int for value in self.fingertip)):
            raise ValueError("fingertip must be an integer pixel pair")
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ValueError("confidence must be a number")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if self.gesture not in {"point", "pinch", "open", "unknown"}:
            raise ValueError("unsupported gesture")
        if type(self.track_id) is not int or self.track_id < 0:
            raise ValueError("track_id must be a nonnegative integer")


def _is_pointing(landmarks: Iterable[Any]) -> bool:
    """Use a conservative geometry heuristic to label an extended index finger."""
    points = list(landmarks)
    if len(points) < 21:
        return False
    wrist = points[0]

    def distance(a: Any, b: Any) -> float:
        return ((float(a.x) - float(b.x)) ** 2 + (float(a.y) - float(b.y)) ** 2) ** 0.5

    index_extended = distance(wrist, points[8]) > distance(wrist, points[6]) * 1.08
    other_extended = sum(
        distance(wrist, points[tip]) > distance(wrist, points[pip]) * 1.08
        for tip, pip in ((12, 10), (16, 14), (20, 18))
    )
    return index_extended and other_extended <= 1


def cell_from_point(point: tuple[int, int] | None, board: BoardRect) -> int | None:
    """Map an image point to a row-major cell, or None outside the overlay."""
    if point is None:
        return None
    if (not isinstance(point, tuple) or len(point) != 2 or
            any(type(value) is not int for value in point)):
        raise ValueError("point must be a pair of integer pixels or None")
    x, y = point
    if not (board.left <= x < board.left + board.side and
            board.top <= y < board.top + board.side):
        return None
    col = min(2, (x - board.left) * 3 // board.side)
    row = min(2, (y - board.top) * 3 // board.side)
    return row * 3 + col


_DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "hand_landmarker.task"
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


class HandTracker:
    """MediaPipe Hand Landmarker wrapper (21 landmarks, no face segmentation).

    ``observe`` exposes the confidence and pointing label needed by the shared
    intent gate; ``detect`` remains a backwards-compatible fingertip-only
    helper for callers that only need the overlay point.
    """

    def __init__(self, model_path: str | Path = _DEFAULT_MODEL):
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise RuntimeError(
                f"Hand model not found at {self.model_path}. "
                "Run `python -m robotlab download-model` first."
            )
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise RuntimeError(
                "Hand tracking needs MediaPipe. Install with: "
                "python -m pip install -e \".[webcam,hand-model]\""
            ) from exc
        # Some Windows builds of the MediaPipe task runtime mishandle non-ASCII
        # paths (the workspace is named Björn). Stage the bundle under the
        # ASCII temp directory before passing it to the native runtime.
        staged_model = Path(tempfile.gettempdir()) / "robotlab-hand-landmarker.task"
        if (not staged_model.is_file() or
                staged_model.stat().st_size != self.model_path.stat().st_size):
            shutil.copyfile(self.model_path, staged_model)
        self._mp = mp
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(staged_model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def observe(self, frame: Any, region: BoardRect | None = None,
                timestamp_ms: int = 0) -> HandObservation | None:
        """Return fingertip, confidence and a conservative pointing label."""
        if frame is None or getattr(frame, "ndim", 0) != 3:
            raise ValueError("frame must be a BGR image")
        if region is not None and not isinstance(region, BoardRect):
            raise ValueError("region must be a BoardRect or None")
        cv2 = _require_cv2()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = max(int(timestamp_ms), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.hand_landmarks:
            return None
        landmarks = result.hand_landmarks[0]
        tip = landmarks[8]  # INDEX_FINGER_TIP in MediaPipe's 21-point model.
        point = (min(frame.shape[1] - 1, max(0, round(tip.x * frame.shape[1]))),
                 min(frame.shape[0] - 1, max(0, round(tip.y * frame.shape[0]))))
        if region is not None and cell_from_point(point, region) is None:
            return None
        confidence = 0.9
        handedness = getattr(result, "handedness", None)
        if handedness:
            category = handedness[0][0] if handedness[0] else None
            score = getattr(category, "score", None)
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                confidence = min(1.0, max(0.0, float(score)))
        return HandObservation(point, confidence, "point" if _is_pointing(landmarks) else "unknown")

    def detect(self, frame: Any, region: BoardRect | None = None,
               timestamp_ms: int = 0) -> tuple[int, int] | None:
        """Return the index fingertip pixel (landmark 8), filtered to region."""
        observation = self.observe(frame, region, timestamp_ms)
        return observation.fingertip if observation else None


def detect_fingertip(frame: Any, region: BoardRect | None = None,
                     tracker: HandTracker | None = None,
                     timestamp_ms: int = 0) -> tuple[int, int] | None:
    """Detect a real hand landmark; kept as a small convenience API.

    Pass a reused ``HandTracker`` in a video loop. Without one, this creates and
    closes a tracker for one frame and is intended only for small experiments.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        raise ValueError("frame must be a BGR image")
    if region is not None and not isinstance(region, BoardRect):
        raise ValueError("region must be a BoardRect or None")
    if tracker is not None:
        return tracker.detect(frame, region, timestamp_ms)
    with HandTracker() as own_tracker:
        return own_tracker.detect(frame, region, timestamp_ms)


def intent_from_observation(observation: HandObservation | None,
                            board: BoardRect | BoardCalibration,
                            *, timestamp_ms: int) -> HandIntent | None:
    """Convert a camera observation into the normalized intent contract."""
    if observation is None:
        return None
    if isinstance(board, BoardRect):
        coordinates = normalized_from_pixel(observation.fingertip, left=board.left,
                                            top=board.top, side=board.side)
    elif isinstance(board, BoardCalibration):
        coordinates = board.normalized(observation.fingertip)
    else:
        raise ValueError("board must be a BoardRect or BoardCalibration")
    if coordinates is None:
        return None
    return HandIntent(*coordinates, observation.confidence, timestamp_ms,
                      gesture=observation.gesture, track_id=observation.track_id)


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "Webcam mode needs OpenCV. Install it with: "
            "python -m pip install -e .[webcam]"
        ) from exc
    return cv2


def run_webcam(camera_index: int = 0, *, stable_frames: int = 12,
               model_path: str | Path = _DEFAULT_MODEL) -> dict[str, Any]:
    """Run the local webcam game until win/draw or the user presses Q/Esc."""
    if type(camera_index) is not int or camera_index < 0:
        raise ValueError("camera_index must be a nonnegative integer")
    if type(stable_frames) is not int or stable_frames < 1:
        raise ValueError("stable_frames must be a positive integer")
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Could not open webcam index {camera_index}")
    session = Session()
    gate = IntentGate(stable_frames=stable_frames)
    message = "Point at a cell and hold steady"
    with HandTracker(model_path) as tracker:
      try:
        while session.board.next_player == "X":
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Webcam frame could not be read")
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            side = max(3, int(min(width, height) * 0.62))
            rect = BoardRect((width - side) // 2, (height - side) // 2, side)
            timestamp_ms = session.clock()
            observation = tracker.observe(frame, rect, timestamp_ms=timestamp_ms)
            fingertip = observation.fingertip if observation else None
            intent = intent_from_observation(observation, rect, timestamp_ms=timestamp_ms)
            if intent is None:
                gate.reset()
                message = "Show one pointing hand over an empty cell"
            else:
                state = session.state()
                decision = gate.update(intent, now_ms=timestamp_ms,
                                       legal_cells=set(state["legal_moves"]))
                if decision.status == "accepted":
                    state = session.state()
                    session.submit(make_command(state, "move", cell=decision.cell))
                    state = session.state()
                    if state["next_player"] == "O":
                        session.submit(make_command(state, "robot_move"))
                    gate.reset()
                    message = "Move accepted; point at your next cell"
                elif decision.status == "confirming":
                    message = (f"Cell {decision.cell}: hold steady "
                               f"({decision.stable_frames}/{stable_frames})")
                else:
                    message = f"Intent blocked: {decision.reason}"
            _draw_frame(cv2, frame, rect, session.state(), fingertip, message)
            cv2.imshow("RobotLab webcam - simulation only", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
        final_state = session.state()
        # Keep the final board visible until a key is pressed.
        if final_state["winner"] or final_state["is_draw"]:
            message = "Draw" if final_state["is_draw"] else f"Winner: {final_state['winner']}"
            ok, frame = capture.read()
            if ok:
                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                side = max(3, int(min(width, height) * 0.62))
                rect = BoardRect((width - side) // 2, (height - side) // 2, side)
                _draw_frame(cv2, frame, rect, final_state, None, message)
                cv2.imshow("RobotLab webcam - simulation only", frame)
                cv2.waitKey(800)
        return {"simulation_only": True, "final_state": final_state,
                "ended_by_user": not bool(final_state["winner"] or final_state["is_draw"])}
      finally:
          capture.release()
          cv2.destroyAllWindows()


def download_model(model_path: str | Path = _DEFAULT_MODEL) -> Path:
    """Download the official MediaPipe float16 hand-landmarker bundle."""
    from urllib.request import urlopen

    destination = Path(model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(_MODEL_URL, timeout=30) as response:
        data = response.read()
    if len(data) < 1_000_000:
        raise RuntimeError("Downloaded hand model is unexpectedly small")
    destination.write_bytes(data)
    return destination


def _draw_frame(cv2, frame, rect, state, fingertip, message):
    side = rect.side
    for index in (1, 2):
        offset = rect.left + index * side // 3
        cv2.line(frame, (offset, rect.top), (offset, rect.top + side), (0, 220, 255), 2)
        offset = rect.top + index * side // 3
        cv2.line(frame, (rect.left, offset), (rect.left + side, offset), (0, 220, 255), 2)
    cv2.rectangle(frame, (rect.left, rect.top),
                  (rect.left + side, rect.top + side), (0, 220, 255), 3)
    for index, symbol in enumerate(state["board"]):
        if symbol:
            row, col = divmod(index, 3)
            x = rect.left + (col * 2 + 1) * side // 6
            y = rect.top + (row * 2 + 1) * side // 6
            cv2.putText(frame, symbol, (x - side // 14, y + side // 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.4, (40, 40, 255), 4, cv2.LINE_AA)
    if fingertip is not None:
        cv2.circle(frame, fingertip, 10, (0, 255, 0), -1)
    cv2.putText(frame, "SIMULATION ONLY - Q/Esc quits", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, message, (20, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
