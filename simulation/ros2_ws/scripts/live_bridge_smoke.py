"""Send synthetic frames from Windows to an already-running local live receiver."""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from robotlab.webcam_robot import request


def main():
    deadline = time.monotonic() + 45
    while True:
        try:
            status = request('/status')
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    clock_offset = status['clock_offset_ms']
    if status['busy']:
        raise RuntimeError('Receiver already executing a command')
    base_sequence = status['last_sequence'] + 1
    for sequence in range(base_sequence, base_sequence + 12):
        packet = {'run_id': status['run_id'], 'sequence': sequence,
                  'timestamp_ms': int(time.time() * 1000) + clock_offset,
                  'intent': {'x': 0.5, 'y': 0.5, 'confidence': 0.98,
                             'gesture': 'point', 'track_id': 1}}
        response = request('/intent', packet)
        clock_offset = request('/status')['clock_offset_ms']
        time.sleep(0.1)
    if response['stage'] != 'accepted':
        raise RuntimeError(f'Intent not accepted: {response}')
    print('Synthetic pointing accepted by WSL receiver', flush=True)
    pick_mode = status.get('mode') == 'pick_place'
    deadline = time.monotonic() + (150 if pick_mode else 90)
    while time.monotonic() < deadline:
        status = request('/status')
        clock_offset = status['clock_offset_ms']
        if not status['busy']:
            break
        time.sleep(0.5)
    expected_stage = 'placement_verified' if pick_mode else 'hover_verified'
    if status['stage'] != expected_stage:
        raise RuntimeError(f'Execution not verified: {status}')
    packet['sequence'] = base_sequence + 12
    packet['timestamp_ms'] = int(time.time() * 1000) + clock_offset
    if request('/intent', packet)['stage'] != ('complete' if pick_mode else 'release'):
        raise RuntimeError('Held hand could trigger a repeated motion')
    packet['sequence'] = base_sequence + 13
    packet['intent'] = None
    packet['timestamp_ms'] = int(time.time() * 1000) + clock_offset
    request('/intent', packet)
    if pick_mode:
        packet['sequence'] += 1
        packet['intent'] = {'x': 0.2, 'y': 0.2, 'confidence': 0.98, 'gesture': 'point', 'track_id': 1}
        packet['timestamp_ms'] = int(time.time() * 1000) + clock_offset
        if request('/intent', packet)['stage'] != 'complete' or request('/status')['board'][4] != 'X':
            raise RuntimeError('Consumed token was reusable or observed board missing')
    print(f'Windows -> WSL -> MoveIt -> UR5e {expected_stage}; repeated command rejected')


if __name__ == '__main__':
    main()
