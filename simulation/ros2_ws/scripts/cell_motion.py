"""Plan a downward-facing tool hover above a selected board cell."""
import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from robotlab.moveit_planner import MoveItPlanner, world_boxes, cell_tool_target
from robotlab.ros2_executor import ROS2Executor
from robotlab.telemetry import TelemetryRecorder


def main():
    import rclpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cell', type=int, choices=range(9), default=4)
    parser.add_argument('--check-cells', action='store_true')
    parser.add_argument('--all-cells', action='store_true')
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('robotlab_cell_motion')
    recorder = TelemetryRecorder(ROOT / 'artifacts/cell-motion.jsonl')
    try:
        executor = ROS2Executor(node, recorder)
        start = executor.current_positions(timeout=30.0)
        planner = MoveItPlanner(node)
        world = ROOT / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
        planner.apply_boxes(world_boxes(world))
        if args.check_cells:
            failures = []
            for cell in range(9):
                try:
                    xyz = cell_tool_target(world, cell)
                    solution = planner.solve_tool_pose(start, xyz)
                    if not planner.state_validity(solution).valid:
                        raise RuntimeError('cell_target_collision')
                    path = planner.plan_joints(start, solution)
                    from robotlab.ros2_executor import validate_from_state
                    report = validate_from_state(path, start)
                    if not report.accepted:
                        raise RuntimeError(report.reason)
                    pose = planner.tool_pose(solution)
                    error = math.dist(xyz, (pose.position.x, pose.position.y, pose.position.z))
                    if error > 0.001:
                        raise RuntimeError('ik_pose_error')
                    recorder.record('cell_reachability_verified', cell=cell, position_error_m=error,
                                    point_count=len(path), verification='planned_only')
                    print(f'Cell {cell}: collision-free plan, IK error {error * 1000:.3f} mm', flush=True)
                except RuntimeError as error:
                    failures.append(cell)
                    print(f'Cell {cell}: {error}', flush=True)
            if failures:
                raise RuntimeError(f'unreachable_cells:{failures}')
            return 0
        for cell in range(9) if args.all_cells else [args.cell]:
            current = executor.current_positions()
            target = cell_tool_target(world, cell)
            joints = planner.solve_tool_pose(current, target)
            points = planner.plan_joints(current, joints)
            recorder.record('cell_plan_ready', cell=cell, target_m=target, joint_target=joints)
            measured = executor.execute(points)
            pose = planner.tool_pose(measured)
            observed = (pose.position.x, pose.position.y, pose.position.z)
            error = math.dist(target, observed)
            orientation_error = 2 * math.acos(min(1.0, abs(pose.orientation.x)))
            recorder.record('tool_hover_observed', cell=cell, target_m=target,
                observed_m=observed, position_error_m=error, orientation_error_rad=orientation_error,
                verification='forward_kinematics_from_measured_joints')
            if error > 0.01 or orientation_error > 0.05:
                raise RuntimeError('tool_pose_outside_tolerance')
            print(f'Cell {cell} hover verified: {error * 1000:.2f} mm error', flush=True)
        executor.execute(planner.plan_joints(executor.current_positions(), start))
        print('Returned home')
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
