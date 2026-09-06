"""Play the provisional game through a webcam, with the user as the robot arm.

The camera only selects a board cell. The placement itself remains simulated;
no camera frame is sent anywhere and no physical robot driver is loaded.
OpenCV is imported lazily so the rest of the package stays dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def detect_fingertip(frame: Any) -> tuple[int, int] | None:
    """Return the topmost point of the largest skin-colour contour.

    This deliberately simple baseline is useful for a first demo in stable
    lighting. It is not a safety-rated hand tracker; return None when no large
    enough contour can be found and require the user to keep the hand visible.
    """
    cv2 = _require_cv2()
    import numpy as np

    if frame is None or getattr(frame, "ndim", 0) != 3:
        raise ValueError("frame must be a BGR image")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Broad skin baseline; tune for the room and lighting during the demo.
    mask = cv2.inRange(hsv, np.array([0, 35, 45], dtype=np.uint8),
                       np.array([25, 255, 255], dtype=np.uint8))
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [contour for contour in contours if cv2.contourArea(contour) >= 1200]
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    points = contour.reshape(-1, 2)
    # A raised/pointing hand normally has its fingertip near the contour top.
    top_y = int(points[:, 1].min())
    candidates = points[points[:, 1] <= top_y + max(4, int(frame.shape[0] * 0.015))]
    x = int(round(float(candidates[:, 0].mean())))
    return x, top_y


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "Webcam mode needs OpenCV. Install it with: "
            "python -m pip install -e .[webcam]"
        ) from exc
    return cv2


def run_webcam(camera_index: int = 0, *, stable_frames: int = 12) -> dict[str, Any]:
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
    last_cell = None
    stable_count = 0
    message = "Point at a cell and hold steady"
    try:
        while session.board.next_player == "X":
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Webcam frame could not be read")
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            side = max(3, int(min(width, height) * 0.62))
            rect = BoardRect((width - side) // 2, (height - side) // 2, side)
            fingertip = detect_fingertip(frame)
            cell = cell_from_point(fingertip, rect)
            if cell is not None and cell in session.state()["legal_moves"]:
                if cell == last_cell:
                    stable_count += 1
                else:
                    last_cell, stable_count = cell, 1
                message = f"Cell {cell}: hold {max(0, stable_frames - stable_count)} more frames"
                if stable_count >= stable_frames:
                    state = session.state()
                    session.submit(make_command(state, "move", cell=cell))
                    state = session.state()
                    if state["next_player"] == "O":
                        session.submit(make_command(state, "robot_move"))
                    last_cell, stable_count = None, 0
                    message = "Move accepted; point at your next cell"
            else:
                last_cell, stable_count = None, 0
                message = "Point at an empty cell and hold steady"
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
