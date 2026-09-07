import unittest
from robotlab.live_intent import IntentMailbox


class LiveIntentTests(unittest.TestCase):
    def setUp(self):
        self.box = IntentMailbox(stable_frames=2)

    def frame(self, sequence, intent=True, timestamp=1000):
        return {'run_id': self.box.run_id, 'sequence': sequence, 'timestamp_ms': timestamp,
                'intent': {'x': 0.5, 'y': 0.5, 'confidence': 0.98, 'gesture': 'point',
                           'track_id': 1} if intent else None}

    def test_busy_and_release_prevent_repeated_motion(self):
        self.box.submit(self.frame(1), 1000)
        self.box.submit(self.frame(2), 1000)
        self.assertEqual(self.box.take(), 4)
        self.assertIsNone(self.box.take())
        self.assertEqual(self.box.submit(self.frame(3), 1000)['stage'], 'busy')
        self.box.submit(self.frame(4, intent=False), 1000)
        self.box.finish()
        self.assertEqual(self.box.submit(self.frame(5), 1000)['stage'], 'release')
        self.box.submit(self.frame(6, intent=False), 1000)
        self.box.submit(self.frame(7), 1000)
        self.box.submit(self.frame(8), 1000)
        self.assertEqual(self.box.take(), 4)

    def test_duplicate_and_expired_frames_cannot_confirm(self):
        self.box.submit(self.frame(1), 1000)
        with self.assertRaises(ValueError):
            self.box.submit(self.frame(1), 1000)
        with self.assertRaises(ValueError):
            self.box.submit(self.frame(2), 1600)
        self.assertIsNone(self.box.take())
        self.assertEqual(self.box.submit(self.frame(3, timestamp=1600), 1600)['stage'], 'confirming')

    def test_wrong_run_and_future_frame_are_rejected(self):
        frame = self.frame(1)
        frame['run_id'] = 'old-run'
        with self.assertRaises(ValueError):
            self.box.submit(frame, 1000)
        with self.assertRaises(ValueError):
            self.box.submit(self.frame(2, timestamp=1100), 1000)
        self.assertIsNone(self.box.take())

    def test_pick_place_consumes_token_and_publishes_observed_board(self):
        self.box = IntentMailbox(stable_frames=2, mode='pick_place')
        self.box.submit(self.frame(1), 1000)
        self.box.submit(self.frame(2), 1000)
        self.assertEqual(self.box.take(), 4)
        self.box.report_stage('camera_confirmation')
        self.assertTrue(self.box.snapshot()['busy'])
        self.assertEqual(self.box.snapshot()['board'], [''] * 9)
        self.box.finish()
        self.assertEqual(self.box.snapshot()['stage'], 'placement_verified')
        self.assertEqual(self.box.snapshot()['board'][4], 'X')
        for sequence, present in ((3, True), (4, False), (5, True), (6, True)):
            self.assertEqual(self.box.submit(self.frame(sequence, present), 1000)['stage'], 'complete')
        self.assertIsNone(self.box.take())

    def test_failed_pick_stays_inhibited_after_hand_release(self):
        self.box = IntentMailbox(stable_frames=2, mode='pick_place')
        self.box.submit(self.frame(1), 1000)
        self.box.submit(self.frame(2), 1000)
        self.box.take()
        self.box.finish(error=RuntimeError('camera_placement_not_confirmed'))
        self.assertEqual(self.box.snapshot()['board'], [''] * 9)
        self.box.submit(self.frame(3, False), 1000)
        self.assertEqual(self.box.submit(self.frame(4), 1000)['stage'], 'failed')
        self.assertIsNone(self.box.take())
