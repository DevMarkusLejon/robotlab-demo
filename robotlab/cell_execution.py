"""Execute a planned cell hover and verify tool pose from measured joints."""
import math

from .moveit_planner import cell_tool_target


def hover_cell(executor, planner, world, cell, recorder):
    start = executor.current_positions()
    target = cell_tool_target(world, cell)
    joints = planner.solve_tool_pose(start, target)
    points = planner.plan_joints(start, joints)
    recorder.record('cell_plan_ready', cell=cell, target_m=target, joint_target=joints)
    measured = executor.execute(points)
    pose = planner.tool_pose(measured)
    observed = (pose.position.x, pose.position.y, pose.position.z)
    error = math.dist(target, observed)
    orientation_error = 2 * math.acos(min(1.0, abs(pose.orientation.x)))
    recorder.record('tool_hover_observed', cell=cell, target_m=target, observed_m=observed,
        position_error_m=error, orientation_error_rad=orientation_error,
        verification='forward_kinematics_from_measured_joints')
    if error > 0.01 or orientation_error > 0.05:
        raise RuntimeError('tool_pose_outside_tolerance')
    executor.execute(planner.plan_joints(executor.current_positions(), start))
    return error
