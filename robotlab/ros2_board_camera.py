"""Read real ROS image messages from the Gazebo overhead camera bridge."""
import time

from .board_observer import observe_tokens
from .sim_camera import TOPIC, board_calibration


class ROSBoardCamera:
    def __init__(self, node):
        from sensor_msgs.msg import Image
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        self.node = node
        self.latest = None
        self.received_at = 0.0
        self.subscription = node.create_subscription(Image, TOPIC, self._receive,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))

    def _receive(self, message):
        self.latest = message
        self.received_at = time.monotonic()

    def preview_jpeg(self):
        import cv2
        message = self.latest
        if message is None or time.monotonic() - self.received_at > 1.0:
            return None
        ok, encoded = cv2.imencode('.jpg', self.decode(message))
        return encoded.tobytes() if ok else None

    @staticmethod
    def decode(message):
        import cv2
        import numpy as np
        if message.encoding not in ('rgb8', 'bgr8'):
            raise RuntimeError(f'unsupported_camera_encoding:{message.encoding}')
        rows = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape(message.height, message.step)
        frame = rows[:, :message.width * 3].reshape(message.height, message.width, 3).copy()
        if message.encoding == 'rgb8':
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # Match increasing world-y row numbering used by the robot.
        return cv2.flip(frame, 0)

    def observe(self, timeout=10):
        import rclpy
        # Discard queued frames from a preceding robot movement, then require
        # another sensor timestamp. A cached image cannot confirm placement.
        rclpy.spin_once(self.node, timeout_sec=0.05)
        previous = self._stamp(self.latest) if self.latest else None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            message = self.latest
            if message is None or self._stamp(message) == previous:
                continue
            frame = self.decode(message)
            now = time.monotonic_ns() // 1_000_000
            observation = observe_tokens(frame, board_calibration(),
                frame_id=f'gazebo:{self._stamp(message)}', timestamp_ms=now)
            return observation, frame
        raise TimeoutError('no_fresh_board_camera_image')

    @staticmethod
    def _stamp(message):
        return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
