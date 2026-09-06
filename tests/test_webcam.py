import unittest

from robotlab.webcam import BoardRect, HandObservation, cell_from_point, intent_from_observation


class WebcamMappingTests(unittest.TestCase):
    def setUp(self):
        self.board = BoardRect(100, 50, 300)

    def test_maps_centres_row_major(self):
        self.assertEqual(cell_from_point((150, 100), self.board), 0)
        self.assertEqual(cell_from_point((250, 200), self.board), 4)
        self.assertEqual(cell_from_point((399, 349), self.board), 8)

    def test_edges_and_outside(self):
        self.assertEqual(cell_from_point((100, 50), self.board), 0)
        self.assertEqual(cell_from_point((400, 349), self.board), None)
        self.assertIsNone(cell_from_point(None, self.board))

    def test_rejects_malformed_points_and_rectangles(self):
        with self.assertRaises(ValueError):
            BoardRect(0, 0, 2)
        with self.assertRaises(ValueError):
            cell_from_point([1, 2], self.board)
        with self.assertRaises(ValueError):
            cell_from_point((1, True), self.board)

    def test_detector_rejects_malformed_region_without_a_camera(self):
        from robotlab.webcam import detect_fingertip
        with self.assertRaises(ValueError):
            detect_fingertip(None, region="board")

    def test_observation_bridges_to_the_shared_intent_contract(self):
        observation = HandObservation((250, 200), 0.91, gesture="point", track_id=3)
        intent = intent_from_observation(observation, self.board, timestamp_ms=123)
        self.assertAlmostEqual(intent.x, 150.5 / 300)
        self.assertAlmostEqual(intent.y, 150.5 / 300)
        self.assertEqual((intent.confidence, intent.track_id, intent.timestamp_ms), (0.91, 3, 123))

    def test_observation_rejects_bad_confidence_and_gesture(self):
        with self.assertRaises(ValueError):
            HandObservation((1, 2), 1.1)
        with self.assertRaises(ValueError):
            HandObservation((1, 2), 0.9, gesture="wave")


if __name__ == "__main__":
    unittest.main()
