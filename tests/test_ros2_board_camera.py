import time
import unittest
from types import SimpleNamespace

from robotlab.ros2_board_camera import ROSBoardCamera


class CameraMessageTests(unittest.TestCase):
    def setUp(self):
        try:
            import cv2
            import numpy
        except ImportError:
            self.skipTest('OpenCV/numpy unavailable')

    def test_rgb_padding_and_board_orientation(self):
        # Padding bytes must not become pixels; optical top becomes board bottom.
        message = SimpleNamespace(encoding='rgb8', height=2, width=1, step=4,
                                  data=bytes((255, 0, 0, 99, 0, 0, 255, 99)))
        frame = ROSBoardCamera.decode(message)
        self.assertEqual(frame.shape, (2, 1, 3))
        self.assertEqual(frame[:, 0].tolist(), [[255, 0, 0], [0, 0, 255]])

    def test_missing_or_stale_preview_never_returns_last_good_image(self):
        camera = object.__new__(ROSBoardCamera)
        camera.latest = None
        camera.received_at = time.monotonic()
        self.assertIsNone(camera.preview_jpeg())
        camera.latest = SimpleNamespace(encoding='rgb8', height=1, width=1,
                                       step=3, data=bytes((255, 0, 0)))
        self.assertTrue(camera.preview_jpeg().startswith(b'\xff\xd8'))
        camera.received_at = time.monotonic() - 2
        self.assertIsNone(camera.preview_jpeg())
