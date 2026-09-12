"""Taught joint routes. No Gazebo coordinates or default physical waypoints."""
from dataclasses import dataclass
import json
import math
from numbers import Real
from pathlib import Path

SMC_REVISION = '4efe7bbb00f8e39c72e3a3fd21f2f1f4ded0f0f1'


def vector(values):
    try:
        values = tuple(values)
    except TypeError as error:
        raise ValueError('expected_six_finite_joint_angles_in_radians') from error
    if (len(values) != 6 or any(isinstance(x, bool) or not isinstance(x, Real)
                               or not math.isfinite(x) for x in values)):
        raise ValueError('expected_six_finite_joint_angles_in_radians')
    return tuple(float(x) for x in values)


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'invalid_{name}')
    return float(value)


@dataclass(frozen=True)
class Workcell:
    data: dict

    @classmethod
    def load(cls, path):
        result = cls(json.loads(Path(path).read_text(encoding='utf-8')))
        result.validate()
        return result

    def validate(self):
        d = self.data
        if d.get('schema_version') != 1 or d.get('units') != 'radians':
            raise ValueError('unsupported_workcell_schema_or_units')
        if d.get('smc_revision') != SMC_REVISION:
            raise ValueError('unreviewed_smc_revision')
        for name in ('joint_tolerance', 'settled_velocity', 'motion_timeout_s',
                     'camera_timeout_s', 'max_step_rad'):
            positive(d.get(name), name)
        limits = d.get('joint_limits', [])
        if not isinstance(limits, list) or len(limits) != 6:
            raise ValueError('six_joint_limits_required')
        for pair in limits:
            if (len(pair) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in pair)
                    or pair[0] >= pair[1]):
                raise ValueError('invalid_joint_limits')
        self.check_q(d.get('home'))
        # Five X sources and four O sources: no replenishment teleportation.
        if len(d.get('sources', [])) != 9 or len(d.get('cells', [])) != 9:
            raise ValueError('nine_sources_and_cells_required')
        for route in (*d['sources'], *d['cells']):
            if not isinstance(route, list) or len(route) < 2:
                raise ValueError('route_requires_approach_and_contact')
            previous = self.home
            for point in route:
                q = self.check_q(point)
                if max(abs(a-b) for a, b in zip(previous, q)) > d['max_step_rad']:
                    raise ValueError('route_step_too_large')
                previous = q

    @property
    def home(self):
        return vector(self.data['home'])

    def check_q(self, q):
        q = vector(q)
        if any(not low <= x <= high for x, (low, high) in zip(q, self.data['joint_limits'])):
            raise ValueError('joint_limit_violation')
        return q

    def require_hardware(self):
        self.validate()
        if self.data.get('fixture_only') is not False:
            raise ValueError('offline_fixture_cannot_drive_hardware')
        for key in ('robot_serial', 'tool_id', 'calibration_id', 'routes_reviewed_by',
                    'smc_connection_and_stop_reviewed_by'):
            value = self.data.get(key)
            if not isinstance(value, str) or not value.strip() or value.startswith('REQUIRED'):
                raise ValueError(f'missing_{key}')
        if self.data.get('paths_checked_with_payload_and_all_board_states') is not True:
            raise ValueError('unvalidated_taught_paths')

    def route(self, kind, index):
        if kind not in ('sources', 'cells') or type(index) is not int or not 0 <= index < 9:
            raise ValueError('invalid_route')
        return tuple(self.check_q(q) for q in self.data[kind][index])
