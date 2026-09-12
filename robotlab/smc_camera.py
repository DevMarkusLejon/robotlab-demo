"""Continuously acquired physical board camera; never fabricates observations."""
import threading
import time
import uuid
from .board_observer import observe_tokens


class PhysicalBoardCamera:
    source = 'physical_board_camera'

    def __init__(self, calibration, index=0):
        self.calibration, self.index = calibration, index
        self.condition = threading.Condition()
        self.shutdown = threading.Event()
        self.latest = None
        self.error = None
        self.last_delivered = None
        self.thread = threading.Thread(target=self._capture, daemon=True)
        self.thread.start()

    def _capture(self):
        cap = None
        try:
            import cv2
            from .webcam import HandTracker
            cap = cv2.VideoCapture(self.index)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                raise RuntimeError('camera_unavailable')
            run_id, count = uuid.uuid4().hex, 0
            with HandTracker() as tracker:
                while not self.shutdown.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError('camera_read_failed')
                    timestamp = int(time.monotonic()*1000)
                    hand = tracker.observe(frame, timestamp_ms=timestamp)
                    count += 1
                    observation = observe_tokens(frame, self.calibration,
                        frame_id=f'{run_id}:{count}', timestamp_ms=timestamp,
                        occluded=hand is not None)
                    with self.condition:
                        self.latest = observation
                        self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def observe(self, timeout):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                if self.error is not None:
                    raise RuntimeError('physical_camera_failed') from self.error
                obs = self.latest
                if (obs is not None and obs.frame_id != self.last_delivered
                        and 0 <= int(time.monotonic()*1000)-obs.timestamp_ms <= 500):
                    self.last_delivered = obs.frame_id
                    return obs
                remaining = deadline-time.monotonic()
                if remaining <= 0 or self.shutdown.is_set():
                    raise RuntimeError('no_fresh_physical_camera_frame')
                self.condition.wait(min(remaining, 0.1))

    def close(self):
        self.shutdown.set()
        with self.condition:
            self.condition.notify_all()
        self.thread.join(timeout=2)
