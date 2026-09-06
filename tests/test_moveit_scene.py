from pathlib import Path
import tempfile
import unittest

from robotlab.moveit_planner import world_boxes


class SceneFrameTests(unittest.TestCase):
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
