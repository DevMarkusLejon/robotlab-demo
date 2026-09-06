import json
import tempfile
import unittest
from pathlib import Path

from robotlab.calibration import BoardCalibration
from robotlab.webcam import HandObservation, intent_from_observation


class CalibrationTests(unittest.TestCase):
    def test_rectangle_maps_corners_and_cell_centres(self):
        calibration = BoardCalibration(((100, 50), (400, 50), (400, 350), (100, 350)))
        self.assertAlmostEqual(calibration.normalized((250, 200))[0], 0.5)
        self.assertAlmostEqual(calibration.normalized((250, 200))[1], 0.5)
        self.assertEqual(calibration.cell((250, 200)), 4)
        self.assertEqual(calibration.cell((110, 60)), 0)
        self.assertIsNone(calibration.cell((99, 200)))

    def test_projective_board_maps_a_trapezoid(self):
        calibration = BoardCalibration(((200, 100), (500, 100), (560, 400), (140, 400)))
        self.assertAlmostEqual(calibration.normalized((350, 250))[0], 0.5, places=6)
        self.assertGreater(calibration.normalized((350, 250))[1], 0.5)
        self.assertEqual(calibration.cell((350, 250)), 4)

    def test_degenerate_corners_are_rejected(self):
        with self.assertRaises(ValueError):
            BoardCalibration(((0, 0), (1, 0), (2, 0), (3, 0)))
        with self.assertRaises(ValueError):
            BoardCalibration(((0, 0), (1, 0), (1, 1), (0, 0)))

    def test_calibration_can_feed_the_intent_contract(self):
        calibration = BoardCalibration(((100, 50), (400, 50), (400, 350), (100, 350)))
        intent = intent_from_observation(HandObservation((250, 200), 0.9), calibration,
                                         timestamp_ms=42)
        self.assertAlmostEqual(intent.x, 0.5)
        self.assertAlmostEqual(intent.y, 0.5)
        self.assertEqual(intent.timestamp_ms, 42)

    def test_calibration_can_be_loaded_from_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps({"corners_px": [[0, 0], [3, 0], [3, 3], [0, 3]]}),
                            encoding="utf-8")
            self.assertEqual(BoardCalibration.from_json(path).cell((1.5, 1.5)), 4)


if __name__ == "__main__":
    unittest.main()
