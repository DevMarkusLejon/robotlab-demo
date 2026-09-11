import unittest
from robotlab.metrics import summarize_events


class AttemptMetricsTests(unittest.TestCase):
    def test_failures_and_unverified_completion_remain_in_denominator(self):
        rows = [{'event': 'pick_place_started', 'attempt_id': str(i), 'cell': 4} for i in range(3)]
        rows += [
            {'event': 'placement_observed', 'attempt_id': '0', 'verification': 'camera',
             'frame_id': 'sensor:1', 'accepted': True, 'source': 'gazebo_rendered_camera', 'confirming_frames': 3},
            {'event': 'pick_place_completed', 'attempt_id': '0', 'duration_s': 42},
            {'event': 'pick_place_failed', 'attempt_id': '1'},
            {'event': 'pick_place_completed', 'attempt_id': '2', 'duration_s': 1},
        ]
        result = summarize_events(rows + rows)  # Repeated log imports do not inflate attempts.
        self.assertEqual(result['placement_attempts'], 3)
        self.assertEqual(result['camera_verified_completions'], 1)
        self.assertEqual(result['placement_attempt_success_rate'], 1/3)
        self.assertEqual(result['placement_duration_p50_s'], 42)
        self.assertEqual(result['per_cell']['4']['success_rate'], 1/3)
        self.assertIsNone(result['per_cell']['0']['success_rate'])
