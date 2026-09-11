"""Single-command mailbox for the local webcam-to-simulator bridge."""
from dataclasses import asdict
import threading
import time
import uuid

from .intent import HandIntent, IntentGate
from .match import VerifiedMatch
from .feedback import STAGES, error_message


class IntentMailbox:
    def __init__(self, stable_frames=12, mode='hover'):
        if mode not in ('hover', 'pick_place', 'game'):
            raise ValueError('invalid_mode')
        self.mode = mode
        self.terminal = False
        self.board = [''] * 9
        self.match = VerifiedMatch()
        self.last_frame_ms = None
        self.lock = threading.Lock()
        self.run_id = str(uuid.uuid4())
        self.gate = IntentGate(stable_frames=stable_frames)
        self.sequence = -1
        self.pending = None
        self.pending_at_ms = None
        self.busy = False
        self.latched = False
        self.status = {'stage': 'ready', 'message': STAGES['ready']}

    def snapshot(self):
        with self.lock:
            return dict(self.status, busy=self.busy, run_id=self.run_id,
                        mode=self.mode, terminal=self.terminal, board=list(self.board),
                        winner=self.match.board.winner, is_draw=self.match.board.is_draw,
                        simulation_only=True,
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
            if self.last_frame_ms is not None and now_ms - self.last_frame_ms > 500:
                self.gate.reset()
            self.last_frame_ms = now_ms
            if self.terminal:
                return {'stage': 'failed' if self.status['stage'] == 'failed' else 'complete',
                        'message': self.status['message']}
            if self.busy:
                return {'stage': 'busy', 'message': STAGES['busy']}
            if payload.get('intent') is None:
                self.gate.reset()
                self.latched = False
                self.status = {'stage': 'ready', 'message': STAGES['ready']}
                return dict(self.status)
            if self.latched:
                return {'stage': 'release', 'message': STAGES['release']}
            try:
                intent = HandIntent(**payload['intent'], timestamp_ms=min(timestamp, now_ms))
            except (TypeError, ValueError):
                self.gate.reset()
                raise
            legal = set(self.match.board.legal_moves) if self.mode == 'game' else set(range(9))
            decision = self.gate.update(intent, now_ms=now_ms, legal_cells=legal)
            if decision.status == 'accepted':
                self.pending = decision.cell
                self.pending_at_ms = min(timestamp, now_ms)
                self.busy = True
                self.latched = True
                self.status = {'stage': 'planning', 'cell': decision.cell,
                               'message': STAGES['planning']}
            return dict(asdict(decision), stage=decision.status)

    def take(self, now_ms=None):
        with self.lock:
            cell = self.pending
            self.pending = None
            accepted_at = self.pending_at_ms
            self.pending_at_ms = None
            if (cell is not None and now_ms is not None and
                    (accepted_at is None or now_ms - accepted_at > 500)):
                self.busy = False
                self.terminal = True
                self.status = {'stage': 'failed', 'message': error_message('client_disconnected'),
                               'error_code': 'client_disconnected'}
                return None
            return cell

    def commit_placement(self, receipt, cell):
        with self.lock:
            if self.mode != 'game' or not self.busy:
                raise ValueError('no_game_move_in_progress')
            self.match.commit(receipt, cell)
            self.board = list(self.match.board.cells)

    def next_robot_move(self):
        with self.lock:
            if self.match.board.next_player != 'O':
                return None
            cell = self.match.robot_move()
            self.status = dict(self.status, cell=cell, stage='robot_turn', message=STAGES['robot_turn'])
            return cell

    def finish(self, *, error=None):
        with self.lock:
            self.busy = False
            self.gate.reset()
            if self.mode == 'game':
                self.terminal = bool(error) or self.match.board.next_player is None
                result = ('Du vann!' if self.match.board.winner == 'X' else
                          'Roboten vann.' if self.match.board.winner == 'O' else 'Oavgjort.')
                self.status = dict(self.status,
                    stage='failed' if error else 'complete' if self.terminal else 'placement_verified',
                    error_code=str(error).split(':', 1)[0] if error else None,
                    message=error_message(error) if error else
                    result + ' Välj Nytt spel.' if self.terminal else
                    'Båda placeringarna är bekräftade. Ta bort handen innan nästa drag.')
                return
            if self.mode == 'pick_place':
                self.terminal = True
                if error is None:
                    self.board[self.status['cell']] = 'X'
                self.status = dict(self.status,
                    stage='failed' if error else 'placement_verified',
                    error_code=str(error).split(':', 1)[0] if error else None,
                    message=error_message(error) if error else
                    'Placeringen är bekräftad. Starta igen för en ny pjäs.')
                return
            self.status = {'stage': 'failed' if error else 'hover_verified',
                           'message': str(error) if error else
                           'Tool hover verified. Remove hand from grid before choosing again.'}

    def report_stage(self, stage):
        with self.lock:
            if self.busy:
                self.status = dict(self.status, stage=stage, message=STAGES.get(stage, stage))
