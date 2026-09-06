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


if __name__ == "__main__":
    unittest.main()
