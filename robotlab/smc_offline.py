"""Deterministic contract fixtures, NOT a robot or camera simulation."""
import time
import uuid
from .board_observer import BoardObservation


class OfflineRobot:
    source = 'offline_fixture'

    def __init__(self, workcell, fault=None):
        if workcell.data.get('fixture_only') is not True:
            raise ValueError('offline_requires_fixture_workcell')
        self.workcell, self.fault = workcell, fault
        self.q, self.held, self.token = workcell.home, False, None
        self.cells = [None]*9
        self.moves = []
        self.stops = 0

    def require_home(self):
        if self.q != self.workcell.home:
            raise RuntimeError('not_home')

    def move(self, q):
        if self.fault == 'motion':
            raise RuntimeError('injected_motion_failure')
        self.q = tuple(q)
        self.moves.append(self.q)

    def grasp(self):
        if self.fault == 'grasp':
            raise RuntimeError('injected_grasp_failure')
        index = next((i for i in range(9)
                      if self.q == self.workcell.route('sources', i)[-1]), None)
        if index is None:
            raise RuntimeError('fixture_not_at_source')
        self.token = 'X' if index % 2 == 0 else 'O'
        self.held = True

    def require_held(self):
        if not self.held:
            raise RuntimeError('fixture_payload_lost')

    def open(self):
        if self.held:
            cell = next((i for i in range(9)
                         if self.q == self.workcell.route('cells', i)[-1]), None)
            if cell is None:
                raise RuntimeError('fixture_not_at_cell')
            if self.fault == 'wrong_cell':
                cell = (cell+1) % 9
            self.cells[cell] = self.token
        self.held = False

    def stop(self):
        self.stops += 1


class OfflineCamera:
    source = 'offline_fixture'

    def __init__(self, robot, *, clock=time.monotonic, sleep=time.sleep):
        self.robot = robot
        self.run_id, self.counter = uuid.uuid4().hex, 0
        self.clock, self.sleep = clock, sleep
        self.last_timestamp = -1

    def observe(self, timeout):
        if self.robot.fault == 'camera':
            raise RuntimeError('injected_camera_failure')
        deadline = self.clock() + timeout
        # Windows monotonic clocks can have a coarser resolution than sleep.
        # Wait for a real new timestamp rather than replaying one or inventing it.
        while True:
            now = self.clock()
            if now >= deadline:
                raise RuntimeError('offline_camera_timeout')
            timestamp = int(now * 1000)
            if timestamp > self.last_timestamp:
                break
            self.sleep(min(0.003, deadline - now))
        self.last_timestamp = timestamp
        self.counter += 1
        return BoardObservation(f'{self.run_id}:{self.counter}',
            timestamp, tuple(self.robot.cells))

    def close(self):
        pass
