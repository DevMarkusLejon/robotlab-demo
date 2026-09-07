"""Single-command mailbox for the local webcam-to-simulator bridge."""
from dataclasses import asdict
import threading
import time
import uuid

from .intent import HandIntent, IntentGate


class IntentMailbox:
    def __init__(self, stable_frames=12):
        self.lock = threading.Lock()
        self.run_id = str(uuid.uuid4())
        self.gate = IntentGate(stable_frames=stable_frames)
        self.sequence = -1
        self.pending = None
        self.busy = False
        self.latched = False
        self.status = {'stage': 'ready', 'message': 'Point and hold over a cell'}

    def snapshot(self):
        with self.lock:
            return dict(self.status, busy=self.busy, run_id=self.run_id,
                        rearm_required=self.latched, server_time_ms=int(time.time() * 1000),
                        last_sequence=self.sequence)

    def submit(self, payload, now_ms):
        with self.lock:
            if payload.get('run_id') != self.run_id:
                raise ValueError('wrong_server_run')
            sequence = payload.get('sequence')
            if type(sequence) is not int or sequence <= self.sequence:
                raise ValueError('duplicate_or_old_frame')
            timestamp = payload.get('timestamp_ms')
            if type(timestamp) is not int or not -50 <= now_ms - timestamp <= 500:
                self.gate.reset()
                raise ValueError('stale_or_future_frame')
            self.sequence = sequence
            if self.busy:
                return {'stage': 'busy', 'message': 'Robot is moving; no command queued'}
            if payload.get('intent') is None:
                self.gate.reset()
                self.latched = False
                return {'stage': 'ready', 'message': 'Point and hold over a cell'}
            if self.latched:
                return {'stage': 'release', 'message': 'Move your hand outside the grid to rearm'}
            intent = HandIntent(**payload['intent'], timestamp_ms=min(timestamp, now_ms))
            decision = self.gate.update(intent, now_ms=now_ms, legal_cells=set(range(9)))
            if decision.status == 'accepted':
                self.pending = decision.cell
                self.busy = True
                self.latched = True
                self.status = {'stage': 'planning', 'cell': decision.cell,
                               'message': f'Planning hover above cell {decision.cell + 1}'}
            return dict(asdict(decision), stage=decision.status)

    def take(self):
        with self.lock:
            cell = self.pending
            self.pending = None
            return cell

    def finish(self, *, error=None):
        with self.lock:
            self.busy = False
            self.gate.reset()
            self.status = {'stage': 'failed' if error else 'hover_verified',
                           'message': str(error) if error else
                           'Tool hover verified. Remove hand from grid before choosing again.'}
