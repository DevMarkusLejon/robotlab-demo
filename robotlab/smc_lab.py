"""Reference lab factory for the inspected SMC + Robotiq socket interface.

No connection occurs on import. Use a different lab factory for RS485/OnRobot.
This profile must be completed and reviewed for the actual installation.
"""
from pathlib import Path
import subprocess
import time
from .smc_adapter import SMCRobot
from .smc_workcell import SMC_REVISION, positive, vector


class RobotiqFeedback:
    def __init__(self, gripper, settings, *, clock=time.monotonic, sleep=time.sleep):
        self.gripper, self.settings = gripper, settings
        self.clock, self.sleep = clock, sleep
        for key in ('open_position', 'closed_position', 'speed', 'force'):
            value = settings.get(key)
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError(f'invalid_gripper_{key}')
        if settings['open_position'] >= settings['closed_position']:
            raise ValueError('invalid_gripper_position_order')
        positive(settings.get('timeout_s'), 'gripper_timeout')

    def _move(self, position, expect_object):
        g = self.gripper
        ok, target = g.move(position, self.settings['speed'], self.settings['force'])
        if not ok:
            raise RuntimeError('gripper_command_rejected')
        deadline = self.clock() + self.settings['timeout_s']
        while self.clock() < deadline:
            # PRE prevents accepting a terminal state from the previous command.
            if g._get_var(g.FLT) != 0:
                raise RuntimeError('gripper_fault')
            if g._get_var(g.PRE) == target:
                status = g._get_var(g.OBJ)
                if expect_object and status in (1, 2):
                    return True
                if status == 3:
                    return not expect_object and abs(g.get_current_position()-target) <= 2
            self.sleep(0.02)
        raise RuntimeError('gripper_timeout')

    def open_and_confirm(self):
        return self._move(self.settings['open_position'], False)

    def close_and_confirm_object(self):
        return self._move(self.settings['closed_position'], True)

    def object_held(self):
        return self.gripper._get_var(self.gripper.FLT) == 0 and self.gripper._get_var(self.gripper.OBJ) in (1, 2)


def connect(workcell):
    """Explicit hardware connection, called only after CLI/workcell checks."""
    workcell.require_hardware()
    settings = workcell.data.get('smc', {})
    if settings.get('gripper_interface') != 'robotiq_socket':
        raise ValueError('reference_factory_requires_confirmed_robotiq_socket_interface')
    if settings.get('allow_upstream_speed_slider_and_stop_behavior') is not True:
        raise ValueError('upstream_connection_and_stop_behavior_not_reviewed')
    if not isinstance(settings.get('robot_ip'), str) or not settings['robot_ip'].strip():
        raise ValueError('robot_ip_required')
    for key in ('ctrl_freq', 'max_iterations'):
        if type(settings.get(key)) is not int or settings[key] <= 0:
            raise ValueError(f'invalid_{key}')
    if settings['ctrl_freq'] > 500:
        raise ValueError('invalid_ctrl_freq')
    for key, maximum in (('max_v_percentage', 1), ('acceleration', 1.7)):
        if positive(settings.get(key), key) > maximum:
            raise ValueError(f'invalid_{key}')
    if type(settings.get('gripper_port')) is not int or not 1 <= settings['gripper_port'] <= 65535:
        raise ValueError('gripper_port_required')
    feedback = RobotiqFeedback(None, settings.get('gripper', {}))
    import smc
    # Do not silently bind to another SMC version or a modified checkout.
    root = Path(smc.__file__).resolve().parent
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    if revision != SMC_REVISION or dirty:
        raise ValueError('installed_smc_does_not_match_reviewed_source')
    from smc.bookkeeping.base_config import ConfigBase
    from smc.robots.grippers.robotiq.robotiq_gripper import RobotiqGripper
    cfg = ConfigBase(real=True, robot='ur5e', robot_ip=settings['robot_ip'],
        gripper='none', visualizer=False, plotter=False, save_log=False,
        ctrl_freq=settings['ctrl_freq'], max_iterations=settings['max_iterations'],
        max_v_percentage=settings['max_v_percentage'], acceleration=settings['acceleration'])
    gripper, robot = RobotiqGripper(), None
    try:
        gripper.connect(settings['robot_ip'], settings['gripper_port'])
        # Activation/autocalibration can move fingers: handled in the lab setup,
        # never triggered as a side effect by this adapter.
        if not gripper.is_active():
            raise RuntimeError('activate_gripper_with_lab_procedure_first')
        feedback.gripper = gripper
        robot = smc.getRobotFromConfig(cfg)
        last_timestamp, last_progress = None, time.monotonic()

        def status_check():
            nonlocal last_timestamp, last_progress
            rx = robot._rtde_receive
            timestamp = rx.getTimestamp()
            if timestamp != last_timestamp:
                last_timestamp, last_progress = timestamp, time.monotonic()
            return (time.monotonic()-last_progress < 0.5 and
                    rx.getRobotMode() == 7 and rx.getSafetyMode() == 1)

        def stop():
            # Deliberately uses the same upstream stop implementation, including
            # its freedrive transition; the workcell must record lab review.
            robot.stopRobot()
            deadline = time.monotonic()+2.0
            previous = robot._rtde_receive.getTimestamp()
            while time.monotonic() < deadline:
                current = robot._rtde_receive.getTimestamp()
                if current > previous and max(map(abs, vector(robot._rtde_receive.getActualQd()))) <= workcell.data['settled_velocity']:
                    return True
                time.sleep(0.02)
            return False

        adapter = SMCRobot(robot, cfg, workcell, gripper=feedback,
                           status_check=status_check, stop=stop)
        adapter.disconnect_gripper = gripper.disconnect
        return adapter
    except BaseException:
        try:
            if robot is not None:
                robot.stopRobot()
        finally:
            try:
                gripper.disconnect()
            except Exception:
                pass
        raise
