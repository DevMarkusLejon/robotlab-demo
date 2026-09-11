import json
import unittest
from robotlab.gripper_transport import decode_gripper_output


def message(attached=False, xyz=None):
    return json.dumps({'data': json.dumps({'attached': attached,
        'token_name': 'token_7', 'token_xyz': xyz or [.45, .15, .7435]})}, indent=2)


class GripperTransportTests(unittest.TestCase):
    def test_single_and_burst_output_use_last_complete_state(self):
        self.assertFalse(decode_gripper_output(message())['attached'])
        self.assertFalse(decode_gripper_output(message(True) + '\n' + message(False))['attached'])
        self.assertTrue(decode_gripper_output(message(False) + message(True))['attached'])

    def test_malformed_trailing_or_invalid_state_is_not_silently_ignored(self):
        for output in ('', message() + '\ntruncated', message() + '{',
                       message(attached='false'), message(xyz=[float('nan'), 0, 0]),
                       message(xyz=[0, 0])):
            with self.subTest(output=output), self.assertRaises(ValueError):
                decode_gripper_output(output)
