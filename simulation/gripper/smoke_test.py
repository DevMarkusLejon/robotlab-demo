"""Exercise real Gazebo contact, attachment, carried motion, and release.

The fixture is moved by the test to isolate gripper physics from arm planning.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent


def command(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8).stdout


def state():
    output = command('ign', 'topic', '-t', '/robotlab/gripper/state', '-e', '-n', '1', '--json-output')
    return json.loads(json.loads(output)['data'])


def enable(value):
    command('ign', 'topic', '-t', '/robotlab/gripper/enable', '-m', 'ignition.msgs.Boolean',
            '-p', 'data: ' + ('true' if value else 'false'))


def pose(name, x, z, inverted=False):
    orientation = 'x: 1, w: 0' if inverted else 'w: 1'
    output = command('ign', 'service', '-s', '/world/gripper_test/set_pose',
        '--reqtype', 'ignition.msgs.Pose', '--reptype', 'ignition.msgs.Boolean',
        '--timeout', '3000', '--req',
        f'name: "{name}", position: {{x: {x}, y: 0, z: {z}}}, orientation: {{{orientation}}}')
    if 'data: true' not in output:
        raise RuntimeError(f'Fixture command failed: {output}')


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = state()
        if predicate(last):
            return last
    raise RuntimeError(f'Gripper condition not reached: {last}')


def main():
    env = dict(os.environ)
    env['IGN_GAZEBO_SYSTEM_PLUGIN_PATH'] = str(ROOT / 'build')
    # Keep transport discovery separate from any running UR5e demo.
    env['IGN_PARTITION'] = 'robotlab-gripper-' + str(os.getpid())
    os.environ.update(env)
    log = ROOT / 'build/smoke.log'
    with log.open('w') as output:
        simulator = subprocess.Popen(['ign', 'gazebo', '-s', '-r', str(ROOT / 'contact_test.sdf')],
            env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            time.sleep(2)
            initial = state()
            assert not initial['attached'], initial
            enable(True)
            time.sleep(0.3)
            far = state()
            assert not far['attached'], far
            print('No contact: attachment rejected', flush=True)
            pose('token', 0, 0.34)
            attached = wait_for(lambda s: s['attached'])
            assert attached['contact_steps_at_attach'] >= 3, attached
            print('Contact detected: token attached', flush=True)
            pose('fixture', 0.2, 0.6, inverted=True)
            carried = wait_for(lambda s: s['attached'] and s['token_xyz'][2] > 0.5
                               and abs(s['token_xyz'][0] - 0.2) < 0.02)
            print('Token moved with inverted fixture', flush=True)
            enable(False)
            released = wait_for(lambda s: not s['attached'] and s['token_xyz'][2] < 0.03)
            evidence = dict(initial=initial, no_contact=far, attached=attached,
                            carried=carried, released=released)
            (ROOT / 'build/evidence.json').write_text(json.dumps(evidence, indent=2))
            print('Release verified: token fell to ground', flush=True)
        finally:
            os.killpg(simulator.pid, signal.SIGINT)
            try:
                simulator.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(simulator.pid, signal.SIGKILL)
                simulator.wait()


if __name__ == '__main__':
    main()
