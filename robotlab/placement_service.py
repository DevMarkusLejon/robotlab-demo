"""One shared game-to-robot contract; board changes need camera evidence."""
import threading
import time
import uuid
from .board_observer import PlacementVerifier
from .match import VerifiedMatch, VerifiedPlacement


class PlacementService:
    def __init__(self, robot, camera, workcell, recorder, *, clock=time.monotonic):
        if robot.source != camera.source:
            raise ValueError('robot_camera_source_mismatch')
        self.match = VerifiedMatch(source=camera.source)
        self.robot, self.camera, self.workcell, self.recorder = robot, camera, workcell, recorder
        self.clock = clock
        self.session_id = uuid.uuid4().hex
        self.revision = 0
        self.failed = False
        self.cache = {}
        self.lock = threading.Lock()

    def place(self, *, session_id, command_id, expected_revision, cell):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('robot_busy')
        started = None
        try:
            if session_id != self.session_id:
                raise ValueError('session_mismatch')
            if not isinstance(command_id, str) or not command_id or len(command_id) > 128:
                raise ValueError('invalid_command_id')
            if type(expected_revision) is not int or type(cell) is not int:
                raise ValueError('invalid_command')
            signature = (expected_revision, cell)
            if command_id in self.cache:
                previous, result = self.cache[command_id]
                if signature != previous:
                    raise ValueError('command_id_conflict')
                return result
            if self.failed:
                raise RuntimeError('session_fault_requires_physical_reconciliation')
            if expected_revision != self.revision:
                raise ValueError('revision_mismatch')
            self.match.board.play(cell)  # Reject illegal cells/finished games before robot I/O.
            symbol = self.match.board.next_player
            attempt = uuid.uuid4().hex
            rec = self.recorder.scoped(attempt_id=attempt, cell=cell, symbol=symbol,
                                       source=self.camera.source, session_id=self.session_id)
            started = self.clock()
            rec.record('pick_place_started')
            self.robot.require_home()
            baseline = self.camera.observe(self.workcell.data['camera_timeout_s'])
            if tuple(x or '' for x in baseline.cells) != self.match.board.cells:
                raise RuntimeError('physical_board_differs_from_committed_board')
            verifier = PlacementVerifier(baseline, cell=cell, symbol=symbol,
                commanded_at_ms=int(self.clock()*1000), stable_frames=3)
            self.robot.open()
            source_route = self.workcell.route('sources', self.revision)
            cell_route = self.workcell.route('cells', cell)
            for q in source_route:
                self.robot.move(q)
            self.robot.grasp()
            for q in (*reversed(source_route[:-1]), self.workcell.home, *cell_route):
                self.robot.require_held()
                self.robot.move(q)
                self.robot.require_held()
            self.robot.open()
            for q in (*reversed(cell_route[:-1]), self.workcell.home):
                self.robot.move(q)
            deadline = self.clock() + self.workcell.data['camera_timeout_s']
            while self.clock() < deadline:
                observation = self.camera.observe(max(0.001, deadline-self.clock()))
                if self.clock() >= deadline:
                    raise RuntimeError('camera_placement_timeout')
                result = verifier.update(observation, now_ms=int(self.clock()*1000))
                if result == 'verified':
                    receipt = VerifiedPlacement(cell, symbol, observation.cells,
                        observation.frame_id, self.camera.source, verifier.stable)
                    self.match.commit(receipt, cell)
                    self.revision += 1
                    result = {'session_id': self.session_id, 'revision': self.revision,
                        'board': self.match.board.cells, 'source': receipt.source,
                        'frame_id': receipt.frame_id, 'attempt_id': attempt}
                    # Offline fixtures deliberately never emit camera-success events.
                    event = ('fixture_placement_observed' if receipt.source == 'offline_fixture'
                             else 'placement_observed')
                    rec.record(event, verification='camera' if receipt.source != 'offline_fixture'
                        else 'fixture', accepted=True, frame_id=receipt.frame_id,
                        confirming_frames=receipt.confirming_frames, cells=receipt.cells)
                    rec.record('pick_place_completed', duration_s=self.clock()-started)
                    self.cache[command_id] = (signature, result)
                    return result
            raise RuntimeError('camera_placement_timeout')
        except BaseException as error:
            if started is not None:
                self.failed = True
                try:
                    self.robot.stop()
                except BaseException as stop_error:
                    rec.record('stop_failed', reason=str(stop_error))
                rec.record('pick_place_failed', reason=str(error), duration_s=self.clock()-started)
            raise
        finally:
            self.lock.release()
