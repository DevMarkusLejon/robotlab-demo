import unittest
from robotlab.board_observer import BoardObservation, PlacementVerifier, observe_tokens
from robotlab.calibration import BoardCalibration


class CameraGameTests(unittest.TestCase):
    def setUp(self):
        try:
            import cv2
            import numpy
        except ImportError:
            self.skipTest('OpenCV/numpy not installed')

    def test_both_colors_at_all_nine_positions_with_existing_tokens(self):
        import cv2
        import numpy as np
        calibration = BoardCalibration(((0, 0), (599, 0), (599, 599), (0, 599)))
        for cell in range(9):
            for symbol, color in [('X', (0, 0, 255)), ('O', (255, 0, 0))]:
                with self.subTest(cell=cell, symbol=symbol):
                    image = np.full((600, 600, 3), 180, dtype=np.uint8)
                    existing = (cell + 1) % 9
                    row, col = divmod(existing, 3)
                    cv2.circle(image, (100 + 200*col, 100 + 200*row), 30, (0, 0, 255), -1)
                    baseline = observe_tokens(image, calibration, frame_id='baseline', timestamp_ms=1000)
                    verifier = PlacementVerifier(baseline, cell=cell, symbol=symbol, commanded_at_ms=1000)
                    row, col = divmod(cell, 3)
                    cv2.circle(image, (100 + 200*col, 100 + 200*row), 30, color, -1)
                    for frame in range(1, 4):
                        observation = observe_tokens(image, calibration, frame_id=str(frame), timestamp_ms=1000+frame)
                        result = verifier.update(observation, now_ms=1000+frame)
                    self.assertEqual(result, 'verified')

    def test_old_token_disappearing_blocks_next_move_confirmation(self):
        baseline = BoardObservation('base', 1000, ('X', None, None, None, None, None, None, None, None))
        verifier = PlacementVerifier(baseline, cell=4, symbol='O', commanded_at_ms=1000)
        for frame in range(1, 5):
            observation = BoardObservation(str(frame), 1000+frame,
                (None, None, None, None, 'O', None, None, None, None))
            self.assertEqual(verifier.update(observation, now_ms=1000+frame), 'board_change_mismatch')
        self.assertFalse(verifier.done)
