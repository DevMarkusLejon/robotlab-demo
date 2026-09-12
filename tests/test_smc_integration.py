import copy
import json
from pathlib import Path
from types import SimpleNamespace
import signal
import tempfile
import unittest

from robotlab.smc_workcell import Workcell
from robotlab.smc_adapter import SMCRobot
from robotlab.smc_lab import RobotiqFeedback
from robotlab.smc_offline import OfflineRobot, OfflineCamera
from robotlab.placement_service import PlacementService
from robotlab.match import VerifiedMatch, VerifiedPlacement
from robotlab.telemetry import TelemetryRecorder
from robotlab.metrics import summarize_events

ROOT = Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = Workcell.load(ROOT/'config/smc-offline.json')
        self.robot = OfflineRobot(self.w)
        self.camera = OfflineCamera(self.robot)
        self.rec = TelemetryRecorder(Path(self.tmp.name)/'events.jsonl')
        self.service = PlacementService(self.robot, self.camera, self.w, self.rec)

    def place(self, cell=4, command='one', revision=0):
        return self.service.place(session_id=self.service.session_id, command_id=command,
                                  expected_revision=revision, cell=cell)

    def test_complete_game_and_source_isolation(self):
        from robotlab.game import choose_move
        while not self.service.match.board.is_draw and not self.service.match.board.winner:
            revision = self.service.revision
            self.place(choose_move(self.service.match.board), str(revision), revision)
        self.assertEqual(self.service.revision, 9)
        self.assertEqual(tuple(x or '' for x in self.robot.cells), self.service.match.board.cells)
        self.assertFalse(any(e['event'] == 'placement_observed' for e in self.rec.events))
        self.assertEqual(summarize_events(self.rec.events)['camera_verified_completions'], 0)

    def test_retry_does_not_repeat_robot_motion(self):
        first = self.place()
        moves = len(self.robot.moves)
        self.assertEqual(first, self.place())
        self.assertEqual(moves, len(self.robot.moves))
        with self.assertRaisesRegex(ValueError, 'command_id_conflict'):
            self.place(cell=3)

    def test_bad_revision_and_session_before_io(self):
        with self.assertRaisesRegex(ValueError, 'revision_mismatch'):
            self.place(revision=3)
        with self.assertRaisesRegex(ValueError, 'session_mismatch'):
            self.service.place(session_id='old', command_id='one', expected_revision=0, cell=0)
        self.assertEqual(self.robot.moves, [])

    def test_faults_latch_and_do_not_commit(self):
        for fault in ('motion', 'grasp', 'camera', 'wrong_cell'):
            with self.subTest(fault=fault):
                robot = OfflineRobot(self.w, fault)
                service = PlacementService(robot, OfflineCamera(robot), self.w, self.rec)
                kwargs = dict(session_id=service.session_id, command_id='a', expected_revision=0, cell=4)
                with self.assertRaises(RuntimeError):
                    service.place(**kwargs)
                self.assertEqual(service.revision, 0)
                self.assertTrue(service.failed)
                self.assertGreater(robot.stops, 0)
                before = len(robot.moves)
                kwargs['command_id'] = 'b'
                with self.assertRaisesRegex(RuntimeError, 'reconciliation'):
                    service.place(**kwargs)
                self.assertEqual(before, len(robot.moves))

    def test_camera_baseline_must_match_committed_board(self):
        self.robot.cells[0] = 'X'
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            self.place()
        self.assertFalse(self.robot.moves)

    def test_busy_does_not_queue(self):
        self.service.lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                self.place()
        finally:
            self.service.lock.release()

    def test_physical_match_rejects_simulator_receipt(self):
        match = VerifiedMatch(source='physical_board_camera')
        receipt = VerifiedPlacement(0, 'X', ('X',)+(None,)*8, 'frame', 'gazebo_rendered_camera', 3)
        with self.assertRaises(ValueError):
            match.commit(receipt, 0)
        physical = VerifiedPlacement(0, 'X', receipt.cells, 'frame', 'physical_board_camera', 3)
        match.commit(physical, 0)
        self.assertEqual(match.board.cells[0], 'X')

    def test_fixtures_and_incomplete_config_cannot_drive_hardware(self):
        with self.assertRaisesRegex(ValueError, 'fixture'):
            self.w.require_hardware()
        with self.assertRaises(ValueError):
            Workcell.load(ROOT/'config/smc-lab.template.json')

    def test_nonfinite_routes_and_untaught_step_rejected(self):
        d = copy.deepcopy(self.w.data)
        d['cells'][0][0][0] = float('nan')
        with self.assertRaises(ValueError):
            Workcell(d).validate()
        d['cells'][0][0][0] = 2.0
        with self.assertRaisesRegex(ValueError, 'step_too_large'):
            Workcell(d).validate()

    def test_physical_metrics_do_not_mix_in_offline_attempts(self):
        events = [
            {'event':'pick_place_started', 'attempt_id':'real', 'cell':4, 'source':'physical_board_camera'},
            {'event':'placement_observed', 'attempt_id':'real', 'source':'physical_board_camera',
             'verification':'camera', 'frame_id':'physical:4', 'accepted':True, 'confirming_frames':3},
            {'event':'pick_place_completed', 'attempt_id':'real', 'duration_s':3, 'source':'physical_board_camera'},
            {'event':'pick_place_started', 'attempt_id':'fixture', 'cell':0, 'source':'offline_fixture'}]
        summary = summarize_events(events)
        self.assertEqual(summary['placement_attempts'], 1)
        self.assertEqual(summary['camera_verified_completions'], 1)

    def test_stale_camera_cannot_commit(self):
        from robotlab.board_observer import BoardObservation
        class StaleCamera(OfflineCamera):
            def observe(inner, timeout):
                obs = super().observe(timeout)
                if inner.counter > 1:
                    return BoardObservation(obs.frame_id, obs.timestamp_ms-1000, obs.cells)
                return obs
        self.service = PlacementService(self.robot, StaleCamera(self.robot), self.w, self.rec)
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            self.place()
        self.assertEqual(self.service.revision, 0)
        self.assertEqual(self.service.match.board.cells, ('',)*9)

    def test_factory_rejects_incomplete_profile_before_importing_smc(self):
        from robotlab.smc_lab import connect
        from unittest.mock import patch
        with patch('importlib.import_module', side_effect=AssertionError('unexpected import')):
            with self.assertRaisesRegex(ValueError, 'fixture'):
                connect(self.w)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('SMC adapter requires numpy')
        d = copy.deepcopy(Workcell.load(ROOT/'config/smc-offline.json').data)
        d.update(fixture_only=False, robot_serial='test', tool_id='test', calibration_id='test',
                 routes_reviewed_by='test', smc_connection_and_stop_reviewed_by='test',
                 paths_checked_with_payload_and_all_board_states=True)
        self.w = Workcell(d)
        self.cfg = SimpleNamespace(real=True, visualizer=False, plotter=False, save_log=False,
            ctrl_freq=100, max_iterations=5, acceleration=0.1, max_v_percentage=0.03)
        self.robot = SimpleNamespace(q=np.zeros(6), v=np.zeros(6),
                                     _updateQ=lambda: None, _updateV=lambda: None)
        self.stops = 0
        self.ready = True
        self.mode = 'ok'
        self.calls = 0
        self.now = 0.0

        def stop():
            self.stops += 1
            return True

        def factory(q, cfg, robot, run):
            self.calls += 1
            self.assertFalse(run)
            signal.signal(signal.SIGINT, lambda *_: None)
            def control(i, past):
                if self.mode == 'interrupt':
                    raise KeyboardInterrupt()
                if self.mode == 'stall':
                    self.now += 1.0
                if self.mode == 'ok':
                    robot.q = q
                return self.mode != 'iterations', {}, {}
            loop = SimpleNamespace(controlLoop=control)
            loop.run_one_iter = lambda i: loop.controlLoop(i, {})[0]
            return loop
        self.adapter = SMCRobot(self.robot, self.cfg, self.w, gripper=None,
            status_check=lambda: self.ready, stop=stop, move_factory=factory,
            clock=lambda: self.now, sleep=lambda dt: setattr(self, 'now', self.now+dt))

    def test_success_uses_actual_smc_signature_and_stops(self):
        previous = signal.getsignal(signal.SIGINT)
        self.adapter.move((0.1,0,0,0,0,0))
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.stops, 1)
        self.assertIs(signal.getsignal(signal.SIGINT), previous)

    def test_already_at_goal_avoids_smc_zero_duration(self):
        self.adapter.move((0,)*6)
        self.assertEqual(self.calls, 0)

    def test_upstream_done_is_not_success_without_observed_target(self):
        self.mode = 'wrong_target'
        with self.assertRaisesRegex(RuntimeError, 'not_observed'):
            self.adapter.move((0.1,0,0,0,0,0))
        self.assertEqual(self.stops, 1)

    def test_iteration_exhaustion_interrupt_stall_and_deadline_stop(self):
        for mode, error in [('iterations', RuntimeError), ('interrupt', KeyboardInterrupt),
                            ('stall', RuntimeError)]:
            self.mode = mode
            before = self.stops
            with self.assertRaises(error):
                self.adapter.move((0.1,0,0,0,0,0))
            self.assertEqual(self.stops, before+1)
        self.mode = 'iterations'
        self.w.data['motion_timeout_s'] = 0.001
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            self.adapter.move((0.1,0,0,0,0,0))

    def test_not_ready_or_outside_route_rejected_before_motion(self):
        self.ready = False
        with self.assertRaisesRegex(RuntimeError, 'not_ready'):
            self.adapter.move((0.1,0,0,0,0,0))
        self.ready = True
        with self.assertRaisesRegex(RuntimeError, 'untaught'):
            self.adapter.move((1,0,0,0,0,0))
        self.assertEqual(self.calls, 0)

    def test_motion_requires_settled_home(self):
        self.robot.q[0] = 0.2
        with self.assertRaisesRegex(RuntimeError, 'home'):
            self.adapter.require_home()


class GripperTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.vars = {'PRE': 10, 'OBJ': 2, 'FLT': 0}
        self.gripper = SimpleNamespace(PRE='PRE', OBJ='OBJ', FLT='FLT',
            move=lambda *a: (True, 10), _get_var=lambda k: self.vars[k],
            get_current_position=lambda: 10)
        self.feedback = RobotiqFeedback(self.gripper,
            dict(open_position=0, closed_position=100, speed=20, force=20, timeout_s=0.1),
            clock=lambda: self.now, sleep=lambda dt: setattr(self, 'now', self.now+dt))

    def test_object_contact_required_not_closed_fingers(self):
        self.assertTrue(self.feedback.close_and_confirm_object())
        self.vars['OBJ'] = 3
        self.assertFalse(self.feedback.close_and_confirm_object())

    def test_old_command_acknowledgement_rejected(self):
        self.vars['PRE'] = 9
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            self.feedback.close_and_confirm_object()

    def test_fault_rejects_grip(self):
        self.vars['FLT'] = 1
        with self.assertRaisesRegex(RuntimeError, 'fault'):
            self.feedback.close_and_confirm_object()


if __name__ == '__main__':
    unittest.main()
