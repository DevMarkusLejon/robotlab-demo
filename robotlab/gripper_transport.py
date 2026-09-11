"""Decode complete Gazebo StringMsg snapshots, including CLI burst output."""
import json
import math


def decode_gripper_output(output):
    decoder = json.JSONDecoder()
    remaining = output.lstrip()
    snapshots = []
    while remaining:
        envelope, end = decoder.raw_decode(remaining)
        state = json.loads(envelope['data'])
        if not isinstance(state, dict) or type(state.get('attached')) is not bool:
            raise ValueError('invalid_gripper_state')
        xyz = state.get('token_xyz')
        if xyz is not None and (not isinstance(xyz, list) or len(xyz) != 3 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz)):
            raise ValueError('invalid_gripper_position')
        snapshots.append(state)
        remaining = remaining[end:].lstrip()
    if not snapshots:
        raise ValueError('empty_gripper_state')
    # `ign topic -n 1` can emit a small burst before its process exits.
    # Parse all complete messages strictly, then use the last received snapshot.
    return snapshots[-1]
