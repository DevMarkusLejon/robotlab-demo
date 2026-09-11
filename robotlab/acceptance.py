"""Repeatable Windows -> WSL simulation acceptance runs with durable results.

python -m robotlab.acceptance --game
python -m robotlab.acceptance --cells --repeats 3
python -m robotlab.acceptance --faults
Synthetic input is explicitly recorded. No physical robot is contacted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid
from urllib.error import HTTPError
from .game import Board, choose_move
from .launcher import ROOT, DISTRO, HIDDEN, wsl_path
from .webcam_robot import request


class SimulationSession:
    def __init__(self, game, fault=None):
        self.game = game
        self.fault = fault
        self.process = None
        self.log = None
        key = uuid.uuid4().hex
        self.stop_file = ROOT / f'artifacts/acceptance-{key}.stop'
        self.log_path = ROOT / f'artifacts/acceptance-{key}.log'

    def __enter__(self):
        try:
            request('/status')
        except (OSError, ValueError):
            pass
        else:
            raise RuntimeError('Close the existing RobotLab session before validation')
        self.log_path.parent.mkdir(exist_ok=True)
        self.log = self.log_path.open('w', encoding='utf-8')
        try:
            self.process = subprocess.Popen(['wsl', '-d', DISTRO, '--exec', 'bash',
                wsl_path(ROOT / 'simulation/ros2_ws/scripts/desktop_session.sh'),
                wsl_path(self.stop_file), '--game' if self.game else '--live-pick-place',
                *([self.fault] if self.fault else [])],
                cwd=ROOT, stdout=self.log, stderr=self.log, creationflags=HIDDEN)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('Simulator exited: ' + str(self.log_path))
                try:
                    state = request('/status')
                    if state['mode'] == ('game' if self.game else 'pick_place'):
                        return self
                except (OSError, ValueError):
                    pass
                time.sleep(0.5)
            raise TimeoutError('Simulator startup timed out')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process is not None and self.process.poll() is None:
            self.stop_file.touch()
            self.process.wait()
        self.stop_file.unlink(missing_ok=True)
        if self.log:
            self.log.close()


def send_frame(state, cell=None):
    packet = {'run_id': state['run_id'], 'sequence': state['last_sequence'] + 1,
              'timestamp_ms': int(time.time() * 1000) + state['clock_offset_ms'],
              'input_source': 'synthetic_acceptance', 'intent': None}
    if cell is not None:
        row, col = divmod(cell, 3)
        packet['intent'] = {'x': (col + 0.5) / 3, 'y': (row + 0.5) / 3,
            'confidence': 0.98, 'gesture': 'point', 'track_id': 1}
    return request('/intent', packet)


def probe_rejections():
    """Exercise actual HTTP rejection and hand stability without authorizing motion."""
    def invalid(change, expected):
        state = request('/status')
        packet = {'run_id': state['run_id'], 'sequence': state['last_sequence'] + 1,
            'timestamp_ms': int(time.time()*1000) + state['clock_offset_ms'], 'intent': None}
        packet.update(change(state))
        try:
            request('/intent', packet)
        except HTTPError as error:
            body = json.load(error)
            if error.code != 400 or body.get('error') != expected:
                raise RuntimeError(f'Unexpected protocol rejection: {body}')
        else:
            raise RuntimeError(f'Invalid command was accepted: {expected}')
    invalid(lambda s: {'run_id': 'previous-session'}, 'wrong_server_run')
    invalid(lambda s: {'sequence': s['last_sequence']}, 'duplicate_or_old_frame')
    for _ in range(11):
        if send_frame(request('/status'), 4)['stage'] != 'confirming':
            raise RuntimeError('Pointing accepted too early')
        time.sleep(.1)
    invalid(lambda s: {'timestamp_ms': int(time.time()*1000) + s['clock_offset_ms'] - 800},
            'stale_or_future_frame')
    if send_frame(request('/status'), 4)['stage'] != 'confirming':
        raise RuntimeError('Stale frame did not reset stability')
    # No packets arrive during this outage; the next fresh frame must start over.
    time.sleep(.7)
    result = send_frame(request('/status'), 4)
    if result.get('stable_frames') != 1:
        raise RuntimeError('Packet gap did not reset stability')
    if send_frame(request('/status'), 0).get('stable_frames') != 1:
        raise RuntimeError('Changed target did not reset stability')
    send_frame(request('/status'))
    state = request('/status')
    if state['busy'] or any(state['board']):
        raise RuntimeError('A rejection probe triggered a game move')
    return ['old_session', 'duplicate_frame', 'stale_frame', 'packet_gap', 'changed_target', 'hand_removed']


def play_cell(cell, expected_fault=None):
    state = request('/status')
    send_frame(state)
    for _ in range(12):
        result = send_frame(request('/status'), cell)
        time.sleep(0.1)
    if result['stage'] != 'accepted':
        raise RuntimeError(f'Intent rejected: {result}')
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        state = request('/status')
        if not state['busy']:
            if state['stage'] == 'failed':
                codes = {'camera_unavailable': 'no_fresh_board_camera_image',
                         'grasp_missing': 'grasp_contact_not_confirmed'}
                if (expected_fault and state.get('error_code') == codes[expected_fault]
                        and state['terminal'] and not any(state['board'])):
                    send_frame(state)
                    if send_frame(request('/status'), cell)['stage'] != 'failed':
                        raise RuntimeError('Fault latch released without a scene reset')
                    return state
                raise RuntimeError(str(state.get('error_code')) + ': ' + state['message'])
            if expected_fault:
                raise RuntimeError('Injected fault did not prevent placement')
            if state['board'][cell] != 'X':
                raise RuntimeError('Human placement missing from verified board')
            # Held hands cannot rearm after completion.
            held = send_frame(state, cell)
            if held['stage'] not in ('release', 'complete'):
                raise RuntimeError('Repeated held hand was not inhibited')
            return state
        time.sleep(0.5)
    raise TimeoutError('Game turn timed out')


def run_trial(game, cell=None, fault=None):
    started = time.monotonic()
    row = {'kind': 'fault_rejection' if fault else 'game' if game else 'placement', 'cell': cell,
           'injected_fault': fault,
           'input_source': 'synthetic_acceptance', 'environment': 'gazebo_simulation',
           'success': False}
    session = SimulationSession(game, fault)
    try:
        with session:
            initial = request('/status')
            row['run_id'] = initial['run_id']
            row['loopback_status_rtt_ms'] = round(initial['round_trip_ms'], 3)
            row['protocol_checks'] = probe_rejections()
            transcript = []
            while True:
                chosen = choose_move(Board(tuple(request('/status')['board']))) if game else cell
                state = play_cell(chosen, fault)
                transcript.append({'human_cell': chosen, 'board': state['board']})
                print(json.dumps(transcript[-1]), flush=True)
                if not game or state['terminal']:
                    break
            row.update(success=True, transcript=transcript, winner=state.get('winner'),
                       is_draw=state.get('is_draw'))
    except Exception as error:
        row['error'] = str(error)
    row['duration_s'] = round(time.monotonic() - started, 3)
    row['log'] = str(session.log_path)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--game', action='store_true')
    group.add_argument('--cells', action='store_true')
    group.add_argument('--faults', action='store_true')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--only-cell', type=int, choices=range(9))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    cells = [None] if args.game else [4] if args.faults else [args.only_cell] if args.only_cell is not None else range(9)
    output = ROOT / f'artifacts/acceptance-{time.strftime("%Y%m%d-%H%M%S")}.json'
    rows = []
    for repeat in range(args.repeats):
        for cell in cells:
            for fault in ('camera_unavailable', 'grasp_missing') if args.faults else (None,):
                print(f'Trial {repeat + 1}, cell={cell}, game={args.game}, fault={fault}', flush=True)
                result = run_trial(args.game, cell, fault)
                result['repeat'] = repeat + 1
                rows.append(result)
                output.write_text(json.dumps({'results': rows}, indent=2), encoding='utf-8')
                print(json.dumps(result, ensure_ascii=True), flush=True)
            summary = {'trials': len(rows), 'passed': sum(row['success'] for row in rows),
                       'results': rows, 'manual_pointing_verified': False,
                       'physical_robot_verified': False, 'real_5g_verified': False}
            output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(output), flush=True)
    return int(any(not row['success'] for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
