"""Windows webcam front end for the local ROS2 UR5e demonstration.

Start the WSL live receiver first. Run this module with the webcam environment:
python -m robotlab.webcam_robot
"""
from dataclasses import asdict
import json
import time
import argparse
from pathlib import Path
from urllib.request import Request, urlopen

from .webcam import (HandTracker, BoardRect, _require_cv2, _draw_frame,
                     intent_from_observation)
from .feedback import feedback

URL = 'http://127.0.0.1:8766'


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    req = Request(URL + path, data=data, headers={'Content-Type': 'application/json'})
    started = time.perf_counter()
    with urlopen(req, timeout=0.5) as response:
        result = json.load(response)
    result['round_trip_ms'] = (time.perf_counter() - started) * 1000
    if 'server_time_ms' in result:
        # Windows and WSL wall clocks may differ. Estimate in the server's
        # clock domain; response transit makes this conservatively older.
        result['clock_offset_ms'] = result['server_time_ms'] - int(time.time() * 1000)
    return result


def draw_text(frame, text, xy, size=21):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    font_path = next((str(path) for path in (
        Path('C:/Windows/Fonts/segoeui.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')) if path.exists()), None)
    image = Image.fromarray(frame[:, :, ::-1])
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    ImageDraw.Draw(image).text(xy, text, font=font, fill='white')
    frame[:] = np.asarray(image)[:, :, ::-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-hand', action='store_true', help='Test hand tracking without sending robot commands')
    args = parser.parse_args()
    cv2 = _require_cv2()
    status = request('/status') if not args.check_hand else {
        'run_id': '', 'clock_offset_ms': 0, 'last_sequence': -1, 'board': [''] * 9}
    run_id = status['run_id']
    clock_offset = status['clock_offset_ms']
    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError('Could not open webcam 0')
    sequence = status['last_sequence']
    last_send = 0.0
    last_preview = 0.0
    preview = None
    pick_mode = status.get('mode') in ('pick_place', 'game')
    message = 'Peka på en tom ruta och håll kvar.'
    from .intent import IntentGate
    hand_gate = IntentGate(stable_frames=12)
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
                        if args.check_hand:
                            if intent:
                                decision = hand_gate.update(intent, now_ms=timestamp)
                                message = (f'Ruta {decision.cell + 1}: {decision.stable_frames}/12' if decision.cell is not None else 'Peka i rutnätet.')
                                if decision.status == 'accepted':
                                    message = f'Pekning bekräftad i ruta {decision.cell + 1}. Inget robotkommando skickas.'
                            else:
                                hand_gate.reset()
                                message = 'Visa pekfingret i rutnätet. Inget robotkommando skickas.'
                        else:
                            result = request('/intent', {'run_id': run_id, 'sequence': sequence,
                                'timestamp_ms': timestamp, 'intent': fields, 'input_source': 'windows_mediapipe'})
                            status = request('/status')
                            clock_offset = status['clock_offset_ms']
                            message = feedback(status, result)
                    except (OSError, ValueError) as error:
                        # No retry of an uncertain command. A later fresh frame is
                        # safe because the receiver latches an accepted intent.
                        message = 'Anslutningen saknas. Invänta kontakt eller starta ett nytt spel.'
                    last_send = time.monotonic()
                _draw_frame(cv2, frame, rect, {'board': status.get('board', [''] * 9)},
                    observation.fingertip if observation else None, '')
                cv2.rectangle(frame, (0, 0), (width, 75), (35, 30, 20), -1)
                draw_text(frame, 'RobotLab • Testa pekning' if args.check_hand else 'RobotLab • Tre-i-rad i simulering', (15, 8))
                draw_text(frame, 'Kontrollera rutnummer. Q/Esc stänger testet.' if args.check_hand else
                          'Du är röd (X). Roboten är blå (O). Q/Esc avslutar.', (15, 39), 17)
                if pick_mode:
                    import numpy as np
                    if time.monotonic() - last_preview >= 0.5:
                        try:
                            with urlopen(URL + '/camera.jpg', timeout=0.5) as response:
                                preview = cv2.imdecode(np.frombuffer(response.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
                        except OSError:
                            preview = None
                        last_preview = time.monotonic()
                    panel = cv2.resize(preview, (height, height)) if preview is not None else np.zeros((height, height, 3), dtype=np.uint8)
                    cv2.rectangle(panel, (0, 0), (height, 40), (35, 30, 20), -1)
                    draw_text(panel, 'Brädkamera • Simulering' if preview is not None else 'Brädkameran är inte tillgänglig', (12, 8), 18)
                    frame = np.concatenate((frame, panel), axis=1)
                import textwrap
                cv2.rectangle(frame, (0, height - 65), (frame.shape[1], height), (35, 30, 20), -1)
                for line_no, line in enumerate(textwrap.wrap(message, max(35, frame.shape[1] // 11))[:2]):
                    draw_text(frame, line, (15, height - 60 + line_no * 27), 19)
                cv2.imshow('RobotLab live UR5e webcam', frame)
                key = cv2.waitKey(1) & 0xff
                try:
                    visible = cv2.getWindowProperty('RobotLab live UR5e webcam', cv2.WND_PROP_VISIBLE) >= 1
                except cv2.error:
                    visible = False  # Some backends destroy the window before this query.
                if key in (27, ord('q')) or not visible:
                    break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
