"""Adapter to Marko Guberina's SMC API, with bounded loop execution.

Construction takes an ALREADY configured lab RobotManager. It never constructs
one implicitly: SMC constructors connect, change the speed slider and may
activate/calibrate a gripper. See docs/smc-integration.md.
"""
import signal
import time
from .smc_workcell import vector


class SMCRobot:
    source = 'physical_board_camera'

    def __init__(self, robot, cfg, workcell, *, gripper, status_check,
                 stop, move_factory=None, clock=time.monotonic, sleep=time.sleep):
        workcell.require_hardware()
        if not cfg.real or cfg.visualizer or cfg.plotter or cfg.save_log:
            raise ValueError('requires_real_headless_smc_config')
        if not 0 < cfg.ctrl_freq <= 500:
            raise ValueError('invalid_control_frequency')
        if not 0 < cfg.max_v_percentage <= 1 or not 0 < cfg.acceleration <= 1.7:
            raise ValueError('invalid_smc_motion_limits')
        for callback in (status_check, stop):
            if not callable(callback):
                raise ValueError('lab_status_and_stop_callbacks_required')
        self.robot, self.cfg, self.workcell = robot, cfg, workcell
        self.gripper, self.status_check, self.stop_callback = gripper, status_check, stop
        self.move_factory = move_factory
        self.clock, self.sleep = clock, sleep

    def read_state(self):
        if self.status_check() is not True:
            raise RuntimeError('robot_not_ready')
        start = self.clock()
        # These SMC methods refresh q/v from RTDE; the properties alone are cached.
        self.robot._updateQ()
        self.robot._updateV()
        q, v = self.workcell.check_q(vector(self.robot.q)), vector(self.robot.v)
        if self.clock() - start > 0.5:
            raise RuntimeError('robot_state_read_too_slow')
        return q, v

    def require_home(self):
        q, v = self.read_state()
        if (max(abs(a-b) for a, b in zip(q, self.workcell.home)) > self.workcell.data['joint_tolerance']
                or max(map(abs, v)) > self.workcell.data['settled_velocity']):
            raise RuntimeError('robot_must_start_settled_at_taught_home')

    def move(self, target):
        import numpy as np
        target = self.workcell.check_q(target)
        q, v = self.read_state()
        tolerance = self.workcell.data['joint_tolerance']
        error = max(abs(a-b) for a, b in zip(q, target))
        if error <= tolerance and max(map(abs, v)) <= self.workcell.data['settled_velocity']:
            return  # Also avoids division by zero in SMC moveJPWTraj for q == target.
        if error > self.workcell.data['max_step_rad']:
            raise RuntimeError('untaught_joint_transition')
        if self.move_factory is None:
            from smc.control.joint_space.joint_space_point_to_point import moveJPWTraj
            factory = moveJPWTraj
        else:
            factory = self.move_factory
        old_handler = signal.getsignal(signal.SIGINT)
        deadline = self.clock() + self.workcell.data['motion_timeout_s']
        try:
            loop = factory(np.array(target), self.cfg, self.robot, run=False)
            # SMC installs its own SIGINT handler in the constructor. Restore
            # caller's handler so cancellation reaches our finally block.
            signal.signal(signal.SIGINT, old_handler)
            original = loop.controlLoop

            def guarded_control(i, past):
                if self.clock() >= deadline:
                    raise RuntimeError('motion_timeout')
                if self.clock() - iteration_started > 0.5:
                    raise RuntimeError('control_loop_stalled_before_command')
                if self.status_check() is not True:
                    raise RuntimeError('robot_not_ready')
                self.workcell.check_q(vector(self.robot.q))
                vector(self.robot.v)
                return original(i, past)

            loop.controlLoop = guarded_control
            for i in range(self.cfg.max_iterations):
                iteration_started = self.clock()
                done = loop.run_one_iter(i)
                elapsed = self.clock() - iteration_started
                if elapsed > 0.5:
                    raise RuntimeError('control_loop_stalled')
                if done:
                    break
                self.sleep(max(0.0, 1.0 / self.cfg.ctrl_freq - elapsed))
            else:
                raise RuntimeError('smc_iteration_limit')
        finally:
            signal.signal(signal.SIGINT, old_handler)
            # Invoked on success too; controller completion is not proof of rest.
            self.stop()
        q, v = self.read_state()
        if (max(abs(a-b) for a, b in zip(q, target)) > tolerance
                or max(map(abs, v)) > self.workcell.data['settled_velocity']):
            raise RuntimeError('joint_target_not_observed_settled')

    def open(self):
        if self.gripper.open_and_confirm() is not True:
            raise RuntimeError('gripper_open_not_confirmed')

    def grasp(self):
        if self.gripper.close_and_confirm_object() is not True:
            raise RuntimeError('grasp_not_confirmed')

    def require_held(self):
        if self.gripper.object_held() is not True:
            raise RuntimeError('payload_lost')

    def stop(self):
        if self.stop_callback() is not True:
            raise RuntimeError('stop_not_confirmed')
