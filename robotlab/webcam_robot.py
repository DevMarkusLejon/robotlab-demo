"""Windows webcam front end for the local ROS2 UR5e hover demonstration.

Start the WSL live receiver first. Run this module with the webcam environment:
python -m robotlab.webcam_robot
"""
from dataclasses import asdict
import json
import time
from urllib.request import Request, urlopen

from .webcam import (HandTracker, BoardRect, _require_cv2, _draw_frame,
                     intent_from_observation)

URL = 'http://127.0.0.1:8766'


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    req = Request(URL + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=0.5) as response:
        result = json.load(response)
    if 'server_time_ms' in result:
        # Windows and WSL wall clocks may differ. Estimate in the server's
        # clock domain; response transit makes this conservatively older.
        result['clock_offset_ms'] = result['server_time_ms'] - int(time.time() * 1000)
    return result


def main():
    cv2 = _require_cv2()
    status = request('/status')
    run_id = status['run_id']
    clock_offset = status['clock_offset_ms']
    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError('Could not open webcam 0')
    sequence = status['last_sequence']
    last_send = 0.0
    message = 'Point at a cell and hold. Robot hovers; no token is placed.'
    try:
        with HandTracker() as tracker:
            while True:
                ok, frame = capture.read()
                captured_at = int(time.time() * 1000)
                if not ok:
                    raise RuntimeError('Camera frame unavailable')
                frame = cv2.flip(frame, 1)
                height, width = frame.shape[:2]
                side = int(min(width, height) * 0.62)
                rect = BoardRect((width - side) // 2, (height - side) // 2, side)
                observation = tracker.observe(frame, rect, int(time.monotonic() * 1000))
                if time.monotonic() - last_send >= 0.1:
                    timestamp = captured_at + clock_offset
                    intent = intent_from_observation(observation, rect, timestamp_ms=timestamp)
                    fields = asdict(intent) if intent else None
                    if fields:
                        fields.pop('timestamp_ms')
                    sequence += 1
                    try:
                        result = request('/intent', {'run_id': run_id, 'sequence': sequence,
                            'timestamp_ms': timestamp, 'intent': fields})
                        status = request('/status')
                        clock_offset = status['clock_offset_ms']
                        if status['busy'] or status['rearm_required']:
                            message = status['message']
                        elif result.get('stage') == 'confirming':
                            message = f"Cell {result['cell'] + 1}: hold {result['stable_frames']}/12"
                        else:
                            message = result.get('message', result.get('reason', 'Show a pointing hand'))
                    except (OSError, ValueError) as error:
                        # No retry of an uncertain command. A later fresh frame is
                        # safe because the receiver latches an accepted intent.
                        message = f'Connection unavailable: {type(error).__name__}'
                    last_send = time.monotonic()
                _draw_frame(cv2, frame, rect, {'board': [''] * 9},
                    observation.fingertip if observation else None, message)
                cv2.putText(frame, 'LIVE UR5e - TOOL HOVER ONLY', (20, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
                cv2.imshow('RobotLab live UR5e webcam', frame)
                if cv2.waitKey(1) & 0xff in (27, ord('q')):
                    break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
