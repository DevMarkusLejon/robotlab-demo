from dataclasses import replace
import unittest
from unittest.mock import patch
from robotlab.game import choose_move
from robotlab.match import VerifiedMatch, VerifiedPlacement
from robotlab.live_intent import IntentMailbox
from robotlab.network import NetworkSimulator
from robotlab.token_supply import SimulatedDispenser


def receipt(match, cell, frame):
    return VerifiedPlacement(cell, match.board.next_player,
        tuple(value or None for value in match.board.play(cell).cells),
        frame, 'gazebo_rendered_camera', 3)


class VerifiedMatchTests(unittest.TestCase):
    def test_complete_game_uses_nine_distinct_tokens_and_only_verified_moves(self):
        game = VerifiedMatch()
        tokens = []
        while game.board.next_player:
            tokens.append(game.token_id)
            cell = choose_move(game.board)
            game.commit(receipt(game, cell, str(len(tokens))), cell)
        self.assertTrue(game.board.is_draw)
        self.assertEqual(len(set(tokens)), 9)
        self.assertEqual(game.board.cells.count('X'), 5)
        self.assertEqual(game.board.cells.count('O'), 4)
        with self.assertRaises(ValueError):
            game.commit(receipt(game, 0, 'extra'), 0)

    def test_wrong_or_missing_camera_evidence_never_changes_board(self):
        game = VerifiedMatch()
        good = receipt(game, 4, 'frame')
        for bad in (None, replace(good, cell=0), replace(good, symbol='O'),
                    replace(good, confirming_frames=2), replace(good, frame_id=''),
                    replace(good, source='gazebo_object_pose'),
                    replace(good, cells=(None,) * 9)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                game.commit(bad, 4)
            self.assertEqual(game.board.cells, ('',) * 9)
        game.commit(good, 4)
        with self.assertRaises(ValueError):
            game.commit(receipt(game, 0, 'frame'), 0)
        self.assertEqual(sum(bool(v) for v in game.board.cells), 1)

    def test_uncertain_dispenser_result_cannot_create_duplicate_token(self):
        supply = SimulatedDispenser()
        supply.dispense('token', 'X')
        with patch('robotlab.token_supply.subprocess.run', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                supply.dispense('token_1', 'O')
        with patch('robotlab.token_supply.subprocess.run') as run:
            with self.assertRaises(RuntimeError):
                supply.dispense('token_1', 'O')
            run.assert_not_called()


class GameIntentTests(unittest.TestCase):
    def setUp(self):
        self.box = IntentMailbox(mode='game', stable_frames=2)
        self.seq = 0

    def frame(self, cell=4, now=1000, confidence=.98):
        self.seq += 1
        row, col = divmod(cell or 0, 3)
        return {'run_id': self.box.run_id, 'sequence': self.seq, 'timestamp_ms': now,
            'intent': None if cell is None else {'x': (col + .5)/3, 'y': (row + .5)/3,
                'confidence': confidence, 'track_id': 1, 'gesture': 'point'}}

    def test_changed_target_hand_loss_and_low_confidence_reset_confirmation(self):
        self.box.submit(self.frame(4), 1000)
        self.assertEqual(self.box.submit(self.frame(0), 1000)['stage'], 'confirming')
        self.box.submit(self.frame(None), 1000)
        self.assertEqual(self.box.submit(self.frame(0), 1000)['stage'], 'confirming')
        self.box.submit(self.frame(0, confidence=.2), 1000)
        self.assertEqual(self.box.submit(self.frame(0), 1000)['stage'], 'confirming')
        self.assertIsNone(self.box.take())

    def test_network_outage_requires_new_stability_and_expired_pending_is_rejected(self):
        self.box.submit(self.frame(), 1000)
        self.assertEqual(self.box.submit(self.frame(now=1600), 1600)['stage'], 'confirming')
        self.box.submit(self.frame(now=1700), 1700)
        self.assertIsNone(self.box.take(now_ms=2300))
        self.assertEqual(self.box.snapshot()['stage'], 'failed')

    def test_latency_and_loss_cannot_produce_an_accepted_move(self):
        for network in (NetworkSimulator(latency_ms=600), NetworkSimulator(drop_rate=1)):
            packet = self.frame()
            delivered = network.deliver(packet, sent_at_ms=1000, deadline_ms=1500)
            self.assertFalse(delivered.delivered)
            if delivered.reason != 'packet_loss':
                with self.assertRaises(ValueError):
                    self.box.submit(packet, delivered.delivered_at_ms)
            self.assertIsNone(self.box.take())

    def test_new_busy_frames_cannot_extend_an_accepted_commands_deadline(self):
        self.box.submit(self.frame(), 1000)
        self.box.submit(self.frame(now=1100), 1100)
        self.box.submit(self.frame(now=1500), 1500)
        self.assertIsNone(self.box.take(now_ms=1700))
        self.assertTrue(self.box.snapshot()['terminal'])

    def test_human_and_robot_turn_keep_busy_until_both_camera_receipts(self):
        self.box.submit(self.frame(), 1000)
        self.box.submit(self.frame(), 1000)
        cell = self.box.take()
        self.box.commit_placement(receipt(self.box.match, cell, 'x'), cell)
        robot_cell = self.box.next_robot_move()
        self.assertTrue(self.box.snapshot()['busy'])
        self.assertEqual(self.box.submit(self.frame(8), 1000)['stage'], 'busy')
        self.box.commit_placement(receipt(self.box.match, robot_cell, 'o'), robot_cell)
        self.box.finish()
        self.assertEqual(self.box.submit(self.frame(8), 1000)['stage'], 'release')
        self.box.submit(self.frame(None), 1000)
        self.assertEqual(self.box.submit(self.frame(4), 1000)['stage'], 'rejected')
        self.assertIsNone(self.box.take())

    def test_grasp_or_camera_failure_stops_game_without_inventing_a_move(self):
        for failure in ('grasp_contact_not_confirmed', 'no_fresh_board_camera_image',
                        'camera_placement_not_confirmed'):
            self.setUp()
            self.box.submit(self.frame(), 1000)
            self.box.submit(self.frame(), 1000)
            self.box.take()
            self.box.finish(error=RuntimeError(failure))
            self.assertEqual(self.box.snapshot()['board'], [''] * 9)
            self.box.submit(self.frame(None), 1000)
            self.assertEqual(self.box.submit(self.frame(), 1000)['stage'], 'failed')
            self.assertIsNone(self.box.take())
