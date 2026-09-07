import unittest
from robotlab.board_observer import BoardObservation, PlacementVerifier, observe_tokens
from robotlab.calibration import BoardCalibration


class PlacementEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = BoardObservation('baseline', 1000, (None,) * 9)
        self.verifier = PlacementVerifier(self.baseline, cell=4, symbol='X', commanded_at_ms=1000)

    def observation(self, number, cell=4):
        cells = [None] * 9
        cells[cell] = 'X'
        return BoardObservation(str(number), 1000 + number, tuple(cells))

    def test_three_fresh_frames_are_required(self):
        self.assertEqual(self.verifier.update(self.observation(1), now_ms=1001), 'confirming')
        self.assertEqual(self.verifier.update(self.observation(2), now_ms=1002), 'confirming')
        self.assertEqual(self.verifier.update(self.observation(3), now_ms=1003), 'verified')
        self.assertEqual(self.verifier.update(self.observation(4), now_ms=1004), 'already_verified')

    def test_wrong_cell_and_replayed_frame_reset_confirmation(self):
        first = self.observation(1)
        self.verifier.update(first, now_ms=1001)
        self.assertEqual(self.verifier.update(first, now_ms=1002), 'invalid_or_stale_observation')
        self.assertEqual(self.verifier.update(self.observation(2, cell=0), now_ms=1002), 'board_change_mismatch')
        self.assertFalse(self.verifier.done)

    def test_old_and_occluded_frames_cannot_verify(self):
        self.assertEqual(self.verifier.update(self.observation(1), now_ms=1600), 'invalid_or_stale_observation')
        covered = BoardObservation('covered', 1601, self.observation(1).cells, False, 'occluded')
        self.assertEqual(self.verifier.update(covered, now_ms=1601), 'invalid_or_stale_observation')


class TokenImageTests(unittest.TestCase):
    def setUp(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest('OpenCV/numpy not installed')
        self.cv2, self.np = cv2, np
        self.calibration = BoardCalibration(((0, 0), (599, 0), (599, 599), (0, 599)))

    def image(self):
        return self.np.full((600, 600, 3), 180, dtype=self.np.uint8)

    def observe(self, frame):
        return observe_tokens(frame, self.calibration, frame_id='fixture', timestamp_ms=1000)

    def test_colored_round_tokens_are_mapped_to_cells(self):
        frame = self.image()
        self.cv2.circle(frame, (100, 100), 30, (0, 0, 255), -1)
        self.cv2.circle(frame, (500, 500), 30, (255, 0, 0), -1)
        result = self.observe(frame)
        self.assertTrue(result.valid)
        self.assertEqual(result.cells[0], 'X')
        self.assertEqual(result.cells[8], 'O')
        self.assertEqual(sum(c is not None for c in result.cells), 2)

    def test_two_tokens_or_boundary_token_are_ambiguous(self):
        frame = self.image()
        self.cv2.circle(frame, (65, 100), 22, (0, 0, 255), -1)
        self.cv2.circle(frame, (135, 100), 22, (255, 0, 0), -1)
        self.assertFalse(self.observe(frame).valid)
        frame = self.image()
        self.cv2.circle(frame, (200, 100), 30, (0, 0, 255), -1)
        self.assertFalse(self.observe(frame).valid)
