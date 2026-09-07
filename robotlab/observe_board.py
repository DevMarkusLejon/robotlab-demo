"""Observe a manually placed colored token through a calibrated webcam.

This is an independent perception test; it does not command the robot.
"""
import argparse
import time
import uuid
from pathlib import Path

from .board_observer import observe_tokens, PlacementVerifier
from .calibration import BoardCalibration
from .telemetry import TelemetryRecorder
from .webcam import HandTracker, _require_cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration', type=Path, required=True)
    parser.add_argument('--cell', type=int, choices=range(9), required=True)
    parser.add_argument('--symbol', choices=('X', 'O'), default='X')
    parser.add_argument('--camera', type=int, default=0)
    args = parser.parse_args()
    calibration = BoardCalibration.from_json(args.calibration)
    cv2 = _require_cv2()
    camera = cv2.VideoCapture(args.camera)
    recorder = TelemetryRecorder('artifacts/board-observer.jsonl')
    run_id = str(uuid.uuid4())
    frame_number = 0
    verifier = None
    message = 'Remove hands. Press B to capture baseline; Q quits.'
    try:
        if not camera.isOpened():
            raise RuntimeError('camera_unavailable')
        with HandTracker() as tracker:
            while True:
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError('camera_read_failed')
                timestamp = int(time.monotonic() * 1000)
                frame_number += 1
                hand = tracker.observe(frame, timestamp_ms=timestamp)
                observation = observe_tokens(frame, calibration, frame_id=f'{run_id}:{frame_number}',
                    timestamp_ms=timestamp, occluded=hand is not None)
                if verifier is not None:
                    result = verifier.update(observation, now_ms=int(time.monotonic() * 1000))
                    message = f'Cell {args.cell + 1}: {result}; remove hand after placing token'
                    if result == 'verified':
                        recorder.record('placement_observed', verification='camera', accepted=True,
                            frame_id=observation.frame_id, cell=args.cell, symbol=args.symbol,
                            cells=observation.cells, confirming_frames=verifier.required,
                            calibration=str(args.calibration), experiment='manual_token_placement')
                        message = 'PLACEMENT VERIFIED. B starts a new baseline; Q quits.'
                        verifier = None
                cv2.putText(frame, message, (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                            0.52, (0, 0, 0), 3)
                cv2.putText(frame, message, (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                            0.52, (255, 255, 255), 1)
                cv2.imshow('RobotLab token observer - manual perception test', frame)
                key = cv2.waitKey(1) & 0xff
                if key in (27, ord('q')):
                    break
                if key == ord('b'):
                    try:
                        verifier = PlacementVerifier(observation, cell=args.cell,
                            symbol=args.symbol, commanded_at_ms=int(time.monotonic() * 1000))
                        message = 'Place token, then remove your hand'
                    except ValueError as error:
                        message = str(error)
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
