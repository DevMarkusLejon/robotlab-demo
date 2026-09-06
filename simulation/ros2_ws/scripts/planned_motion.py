"""Verify MoveIt plans in the Gazebo scene and rejects an enclosing obstacle."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from robotlab.moveit_planner import MoveItPlanner, world_boxes
from robotlab.ros2_executor import ROS2Executor
from robotlab.telemetry import TelemetryRecorder


def main():
    import rclpy
    rclpy.init()
    node = rclpy.create_node('robotlab_planned_motion')
    recorder = TelemetryRecorder(ROOT / 'artifacts/moveit-motion.jsonl')
    try:
        executor = ROS2Executor(node, recorder)
        start = executor.current_positions(timeout=30.0)
        planner = MoveItPlanner(node)
        world = ROOT / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
        planner.apply_boxes(world_boxes(world))
        if not planner.state_validity(start).valid:
            raise RuntimeError('initial_scene_collision')
        target = (start[0] + 0.2, *start[1:])
        points = planner.plan_joints(start, target)
        recorder.record('moveit_plan_ready', point_count=len(points))
        executor.execute(points)
        points = planner.plan_joints(executor.current_positions(), start)
        executor.execute(points)
        planner.apply_boxes([('blocking_obstacle', (3.0, 3.0, 3.0), (0.0, 0.0, 0.5))])
        blocked_state = executor.current_positions()
        validity = planner.state_validity(blocked_state)
        contacts = [(c.contact_body_1, c.contact_body_2) for c in validity.contacts]
        if validity.valid or not any('blocking_obstacle' in pair for pair in contacts):
            raise RuntimeError('blocking_obstacle_collision_not_observed')
        recorder.record('collision_contacts_observed', contacts=contacts)
        try:
            planner.plan_joints(blocked_state, target)
        except RuntimeError as error:
            if str(error) not in ('moveit_plan_rejected:-10', 'moveit_plan_rejected:-26'):
                raise
            recorder.record('collision_test_rejected', reason=str(error))
        else:
            raise RuntimeError('MoveIt accepted a motion inside a blocking obstacle')
        print('MoveIt motion and obstacle rejection verified')
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
