import unittest

from robotlab.webcam import BoardRect, cell_from_point


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


if __name__ == "__main__":
    unittest.main()
