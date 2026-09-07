import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


class PickSceneTests(unittest.TestCase):
    def test_supply_rest_pose_matches_physics_geometry(self):
        path = Path(__file__).parents[1] / 'simulation/ros2_ws/scripts/pick_place.py'
        spec = importlib.util.spec_from_file_location('pick_place', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.WORLD = Path(directory) / 'world.sdf'
            module.prepare_world()
            world = ET.parse(module.WORLD).getroot().find('world')
            supply = world.find("model[@name='supply']")
            pose = [float(v) for v in supply.findtext('pose').split()]
            size = [float(v) for v in supply.findtext('link/collision/geometry/box/size').split()]
            token = world.find("model[@name='token']")
            thickness = float(token.findtext('link/collision/geometry/cylinder/length'))
            self.assertAlmostEqual(pose[2] + size[2] / 2 + thickness / 2, module.SUPPLY[2])
            self.assertEqual(tuple(pose[:2]), module.SUPPLY[:2])
            board = world.find("model[@name='board']")
            board_y = float(board.findtext('pose').split()[1])
            board_size_y = float(board.findtext('link/collision/geometry/box/size').split()[1])
            self.assertLess(pose[1] + size[1] / 2, board_y - board_size_y / 2)
            self.assertIsNotNone(world.find("model[@name='ground']"))
            self.assertIsNotNone(world.find("model[@name='worktable']"))
