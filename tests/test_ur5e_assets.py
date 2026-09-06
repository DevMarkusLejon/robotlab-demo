import json
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from robotlab.safety import UR5E_JOINTS


class UR5eAssetTests(unittest.TestCase):
    def test_world_contains_reference_robot_camera_and_all_six_joints(self):
        path = Path(__file__).parents[1] / "simulation" / "ur5e" / "world.sdf"
        root = ET.parse(path).getroot()
        model = root.find(".//model[@name='ur5e_reference']")
        self.assertIsNotNone(model)
        joints = {joint.attrib["name"] for joint in model.findall("joint")}
        self.assertTrue(set(UR5E_JOINTS).issubset(joints))
        camera = root.find(".//sensor[@name='board_camera']")
        self.assertIsNotNone(camera)

    def test_reference_constants_keep_official_joint_order(self):
        path = Path(__file__).parents[1] / "simulation" / "ur5e" / "ur5e_reference.json"
        reference = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(reference["model"], "UR5e")
        self.assertEqual(reference["joints"], list(UR5E_JOINTS))
        self.assertAlmostEqual(reference["kinematics_m"]["forearm_x"], -0.425)

    def test_generator_is_checked_in_and_points_at_ur_description(self):
        path = Path(__file__).parents[1] / "simulation" / "ur5e" / "generate_official_sdf.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("ur_description", text)
        self.assertIn("sim_ignition:=false", text)


if __name__ == "__main__":
    unittest.main()
