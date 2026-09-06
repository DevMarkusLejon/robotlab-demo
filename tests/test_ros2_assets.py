from pathlib import Path
import unittest


class ROS2AssetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parents[1] / "simulation" / "ros2_ws" / "src" / "robotlab_ur5e_bringup"

    def test_launch_uses_official_ur_description_and_controller_contract(self):
        launch = (self.root / "launch" / "ur5e_gz_ros2.launch.py").read_text(encoding="utf-8")
        self.assertIn("ur_description", launch)
        self.assertIn("sim_ignition:=true", launch)
        self.assertIn("ur5e_arm_controller", launch)

    def test_world_and_moveit_config_are_installed_inputs(self):
        self.assertTrue((self.root / "worlds" / "robotlab_ros2.sdf").is_file())
        moveit = (self.root / "config" / "moveit_controllers.yaml").read_text(encoding="utf-8")
        self.assertIn("FollowJointTrajectory", moveit)
        self.assertEqual(moveit.count("shoulder_pan_joint"), 1)


if __name__ == "__main__":
    unittest.main()
