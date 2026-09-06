from pathlib import Path
import tempfile
import unittest

from robotlab.moveit_planner import world_boxes, cell_tool_target


class SceneFrameTests(unittest.TestCase):
    def test_cell_centers_and_hover_height(self):
        world = Path(__file__).parents[1] / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
        center = cell_tool_target(world, 4)
        self.assertAlmostEqual(center[0], 0.45)
        self.assertAlmostEqual(center[1], 0.0)
        self.assertAlmostEqual(center[2], 0.1375)
        first, last = cell_tool_target(world, 0), cell_tool_target(world, 8)
        self.assertAlmostEqual(last[0] - first[0], 0.45 * 2 / 3)
        self.assertAlmostEqual(last[1] - first[1], 0.45 * 2 / 3)
        for bad in (-1, 9, True, 1.5):
            with self.assertRaises(ValueError):
                cell_tool_target(world, bad)
        for clearance in (-1, 0, float('nan')):
            with self.assertRaises(ValueError):
                cell_tool_target(world, 4, clearance)

    def test_table_and_board_are_transformed_into_robot_frame(self):
        world = Path(__file__).parents[1] / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
        boxes = {name: (size, position) for name, size, position in world_boxes(world)}
        self.assertEqual(boxes['worktable'][0], (1.8, 1.2, 0.12))
        self.assertAlmostEqual(boxes['worktable'][1][2], -0.13)
        self.assertAlmostEqual(boxes['board'][1][2] + boxes['board'][0][2] / 2, -0.0125)
        self.assertAlmostEqual(boxes['ground'][1][2], -0.8)

    def test_unsupported_rotation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'world.sdf'
            path.write_text('<sdf><world><model name="box"><pose>0 0 0 0 0 1</pose>'
                '<link><collision><geometry><box><size>1 1 1</size></box></geometry>'
                '</collision></link></model></world></sdf>')
            with self.assertRaises(ValueError):
                world_boxes(path)
