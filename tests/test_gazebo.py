import math
import unittest

from simulation.gazebo.play_demo import BOARD, joint_angles


class GazeboPlanningTests(unittest.TestCase):
    def test_all_board_cells_have_reachable_joint_targets(self):
        for cell in BOARD:
            angles = joint_angles(cell)
            self.assertEqual(len(angles), 3)
            self.assertTrue(all(math.isfinite(value) for value in angles))

    def test_cell_mapping_is_row_major_and_has_distinct_targets(self):
        targets = [joint_angles(cell) for cell in range(9)]
        self.assertNotEqual(targets[0][0], targets[2][0])
        self.assertNotEqual(targets[0][1:], targets[8][1:])


if __name__ == "__main__":
    unittest.main()
