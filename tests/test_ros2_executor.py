import unittest

from robotlab.ros2_executor import validate_from_state, result_timeout
from robotlab.safety import JointPoint


class MeasuredStartTests(unittest.TestCase):
    def test_simulator_timeout_is_bounded_without_changing_hardware_policy(self):
        self.assertEqual(result_timeout(8), 18)
        self.assertEqual(result_timeout(8, simulation=True), 34)
        self.assertEqual(result_timeout(100, simulation=True), 180)
        with self.assertRaises(ValueError):
            result_timeout(float('nan'), simulation=True)

    def test_first_segment_speed_is_checked(self):
        start = (0, -1, 0, -1, 0, 0)
        target = (1, -1, 0, -1, 0, 0)
        self.assertEqual(validate_from_state((JointPoint(0.1, target),), start).reason, 'speed_limit')

    def test_measured_start_limits_are_checked(self):
        self.assertFalse(validate_from_state((JointPoint(2, (0, -1, 0, -1, 0, 0)),),
                                             (0, 2, 0, -1, 0, 0)).accepted)

    def test_empty_and_instantaneous_paths_are_rejected(self):
        start = (0, -1, 0, -1, 0, 0)
        self.assertFalse(validate_from_state((), start).accepted)
        self.assertFalse(validate_from_state((JointPoint(0, start),), start).accepted)

    def test_reachable_timed_path_is_accepted(self):
        start = (0, -1, 0, -1, 0, 0)
        self.assertTrue(validate_from_state((JointPoint(2, (0.1, -1, 0, -1, 0, 0)),), start).accepted)
