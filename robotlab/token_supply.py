"""Finite simulated dispenser: spawn each new token once; never move existing ones."""
import json
import re
import subprocess
import time


def token_sdf(name, symbol):
    if not re.fullmatch(r'token(?:_[0-8])?', name) or symbol not in ('X', 'O'):
        raise ValueError('invalid_token')
    color = '1 0 0 1' if symbol == 'X' else '0 0 1 1'
    return f'''<sdf version="1.7"><model name="{name}">
      <pose>0.45 -0.36 0.744 0 0 0</pose><link name="token_link">
      <inertial><mass>0.02</mass><inertia><ixx>0.000005</ixx><iyy>0.000005</iyy><izz>0.000009</izz></inertia></inertial>
      <collision name="token_collision"><geometry><cylinder><radius>0.03</radius><length>0.012</length></cylinder></geometry></collision>
      <visual name="token"><geometry><cylinder><radius>0.03</radius><length>0.012</length></cylinder></geometry>
      <material><diffuse>{color}</diffuse></material></visual></link></model></sdf>'''


class SimulatedDispenser:
    """Five red and four blue tokens. The first red token is in the initial world."""
    def __init__(self):
        self.used = set()
        self.remaining = {'X': 5, 'O': 4}

    def dispense(self, name, symbol):
        sdf = token_sdf(name, symbol)
        if name in self.used or self.remaining[symbol] <= 0:
            raise RuntimeError('token_inventory_exhausted')
        # Reserve before the external call: an uncertain spawn is never retried.
        self.used.add(name)
        self.remaining[symbol] -= 1
        if name == 'token':
            if symbol != 'X':
                raise ValueError('first_token_must_be_red')
            return
        result = subprocess.run(['ign', 'service', '-s', '/world/robotlab_ros2/create',
            '--reqtype', 'ignition.msgs.EntityFactory', '--reptype', 'ignition.msgs.Boolean',
            '--timeout', '5000', '--req', 'sdf: ' + json.dumps(sdf) + ', allow_renaming: false'],
            check=True, capture_output=True, text=True, timeout=8)
        if 'data: true' not in result.stdout:
            raise RuntimeError('token_dispenser_failed')
        time.sleep(0.4)  # Let the newly created token settle on its support.
