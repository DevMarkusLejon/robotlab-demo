import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class RobotFloorTests(unittest.TestCase):
    def test_only_demonstration_floor_geometry_is_removed(self):
        path = Path(__file__).parents[1] / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/urdf/render_description.py'
        spec = importlib.util.spec_from_file_location('render_description', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = ET.fromstring(module.remove_builtin_floor('''<robot name="ur">
          <link name="ground_plane"><collision/><visual/><inertial/></link>
          <link name="vacuum_cup"><collision/><visual/></link>
          <link name="base_link"><collision/><visual/></link>
          <joint name="ground_joint" type="fixed"/>
        </robot>'''))
        self.assertIsNone(output.find("link[@name='ground_plane']/collision"))
        self.assertIsNone(output.find("link[@name='ground_plane']/visual"))
        self.assertIsNotNone(output.find("link[@name='ground_plane']/inertial"))
        self.assertIsNotNone(output.find("link[@name='vacuum_cup']/collision"))
        self.assertIsNotNone(output.find("link[@name='base_link']/collision"))
        self.assertIsNotNone(output.find('joint'))
