"""ROS2 trajectory execution with measured start state and result verification.

Requires ROS2 on the executing host. It deliberately does not translate board
coordinates: those must come from a calibrated collision-aware planner.
"""
from __future__ import annotations

import math
import time

from .safety import JointPoint, UR5E_JOINTS, validate_trajectory


def validate_from_state(points, positions):
    """Include the measured start in the speed/limit check, including segment 1."""
    points = tuple(points)
    if not points:
        return validate_trajectory(())
    return validate_trajectory((JointPoint(0.0, tuple(positions)), *points))


def result_timeout(duration_s, simulation=False):
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError('invalid_trajectory_duration')
    # Rendering can slow Gazebo's clock. Keep a bounded simulation-only allowance.
    return min(180.0, max(30.0, 3 * duration_s + 10.0)) if simulation else duration_s + 10.0


class ROS2Executor:
    def __init__(self, node, recorder, *, simulation=False):
        from rclpy.action import ActionClient
        from control_msgs.action import FollowJointTrajectory
        from sensor_msgs.msg import JointState
        self.node = node
        self.recorder = recorder
        self.simulation = simulation
        self.state = None
        self.received_at = 0.0
        self.subscription = node.create_subscription(JointState, '/joint_states', self._state, 10)
        self.client = ActionClient(node, FollowJointTrajectory,
                                   '/ur5e_arm_controller/follow_joint_trajectory')

    def close(self):
        self.client.destroy()
        self.node.destroy_subscription(self.subscription)

    def _state(self, message):
        values = dict(zip(message.name, message.position))
        if all(joint in values and math.isfinite(values[joint]) for joint in UR5E_JOINTS):
            self.state = tuple(values[joint] for joint in UR5E_JOINTS)
            self.received_at = time.monotonic()

    def current_positions(self, timeout=5.0):
        import rclpy
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if self.state is not None and time.monotonic() - self.received_at < 0.5:
                return self.state
        raise RuntimeError('fresh_joint_state_unavailable')

    def _wait(self, future, timeout):
        import rclpy
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        if not future.done():
            raise RuntimeError('action_timeout')
        return future.result()

    def execute(self, points, tolerance=0.03):
        from control_msgs.action import FollowJointTrajectory
        from controller_manager_msgs.srv import ListControllers
        from trajectory_msgs.msg import JointTrajectoryPoint
        points = tuple(points)
        controllers = self.node.create_client(ListControllers, '/controller_manager/list_controllers')
        try:
            if not controllers.wait_for_service(timeout_sec=5.0):
                raise RuntimeError('controller_manager_unavailable')
            deadline = time.monotonic() + 5.0
            while True:
                status = self._wait(controllers.call_async(ListControllers.Request()), 2.0)
                if any(c.name == 'ur5e_arm_controller' and c.state == 'active' for c in status.controller):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('trajectory_controller_inactive')
                time.sleep(0.1)
        finally:
            self.node.destroy_client(controllers)
        if not self.client.wait_for_server(timeout_sec=5.0):
            raise RuntimeError('trajectory_server_unavailable')
        initial = self.current_positions()
        report = validate_from_state(points, initial)
        self.recorder.record('trajectory_checked', accepted=report.accepted, reason=report.reason,
                             measured_start=list(initial))
        if not report.accepted:
            raise RuntimeError(report.reason)
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(UR5E_JOINTS)
        for point in points:
            item = JointTrajectoryPoint()
            item.positions = list(point.positions)
            nanoseconds = round(point.time_s * 1_000_000_000)
            item.time_from_start.sec, item.time_from_start.nanosec = divmod(nanoseconds, 1_000_000_000)
            goal.trajectory.points.append(item)
        handle = self._wait(self.client.send_goal_async(goal), 5.0)
        if not handle.accepted:
            raise RuntimeError('trajectory_goal_rejected')
        try:
            self.recorder.record('execution_started', executor='ros2',
                                 goal_id=[int(value) for value in handle.goal_id.uuid])
            result = self._wait(handle.get_result_async(), result_timeout(points[-1].time_s, self.simulation))
        except BaseException:
            cancellation = self._wait(handle.cancel_goal_async(), 3.0)
            self.recorder.record('execution_cancel_requested', return_code=cancellation.return_code)
            raise
        self.recorder.record('controller_result', status=result.status,
                             error_code=result.result.error_code, reason=result.result.error_string)
        if result.status != 4 or result.result.error_code != 0:
            raise RuntimeError('trajectory_execution_failed')
        # Require a state received after completion, rather than a cached sample.
        self.state = None
        measured = self.current_positions()
        error = max(abs(a - b) for a, b in zip(measured, points[-1].positions))
        self.recorder.record('joint_target_observed', max_error_rad=error,
                             accepted=error <= tolerance, positions=list(measured))
        if error > tolerance:
            raise RuntimeError('final_joint_error')
        return measured
