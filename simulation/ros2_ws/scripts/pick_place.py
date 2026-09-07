"""UR5e contact-gated transfer verified by rendered images and object state."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from robotlab.moveit_planner import MoveItPlanner, world_boxes, cell_tool_target
from robotlab.gripper_scene import allow_cup_contact, set_token, remove_scene_object
from robotlab.ros2_executor import ROS2Executor
from robotlab.telemetry import TelemetryRecorder
from robotlab.sim_camera import add_camera
from robotlab.ros2_board_camera import ROSBoardCamera
from robotlab.board_observer import PlacementVerifier

WORLD = ROOT / 'artifacts/robotlab-pick.sdf'
SUPPLY = (0.45, -0.36, 0.7435)


def prepare_world():
    path = ROOT / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
    tree = ET.parse(path)
    world = tree.getroot().find('world')
    add_camera(world)
    world.append(ET.fromstring('''<model name="supply"><static>true</static><pose>0.45 -0.36 0.70875 0 0 0</pose><link name="supply">
      <collision name="supply"><geometry><box><size>0.12 0.12 0.0575</size></box></geometry></collision>
      <visual name="supply"><geometry><box><size>0.12 0.12 0.0575</size></box></geometry></visual>
    </link></model>'''))
    world.append(ET.fromstring('''<model name="token"><pose>0.45 -0.36 0.744 0 0 0</pose><link name="token_link">
      <inertial><mass>0.02</mass><inertia><ixx>0.000005</ixx><iyy>0.000005</iyy><izz>0.000009</izz></inertia></inertial>
      <collision name="token_collision"><geometry><cylinder><radius>0.03</radius><length>0.012</length></cylinder></geometry></collision>
      <visual name="token"><geometry><cylinder><radius>0.03</radius><length>0.012</length></cylinder></geometry><material><diffuse>1 0 0 1</diffuse></material></visual>
    </link></model>'''))
    WORLD.parent.mkdir(exist_ok=True)
    tree.write(WORLD, encoding='unicode', xml_declaration=True)


def gripper_state():
    result = subprocess.run(['ign', 'topic', '-t', '/robotlab/gripper/state', '-e', '-n', '1',
                             '--json-output'], check=True, capture_output=True, text=True, timeout=5)
    return json.loads(json.loads(result.stdout)['data'])


def suction(enabled):
    subprocess.run(['ign', 'topic', '-t', '/robotlab/gripper/enable', '-m', 'ignition.msgs.Boolean',
                    '-p', f'data: {str(enabled).lower()}'], check=True, timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-world', action='store_true')
    parser.add_argument('--cell', type=int, choices=range(9), default=4)
    args = parser.parse_args()
    if args.prepare_world:
        prepare_world()
        return 0
    import rclpy
    rclpy.init()
    node = rclpy.create_node('robotlab_pick_place')
    recorder = TelemetryRecorder(ROOT / 'artifacts/pick-place.jsonl')
    recorder.record('pick_place_started', cell=args.cell, verification='simulation_only')
    try:
        executor = ROS2Executor(node, recorder)
        home = executor.current_positions(timeout=30)
        planner = MoveItPlanner(node)
        planner.apply_boxes(world_boxes(WORLD))
        allow_cup_contact(planner)
        state = gripper_state()
        if state['attached'] or math.dist(state['token_xyz'], SUPPLY) > 0.02:
            raise RuntimeError('unexpected_initial_token_state')
        set_token(planner, (SUPPLY[0], SUPPLY[1], SUPPLY[2] - 0.75))
        import cv2
        camera = ROSBoardCamera(node)
        baseline, frame = camera.observe(timeout=30)
        cv2.imwrite(str(ROOT / 'artifacts/pick-camera-before.png'), frame)
        verifier = PlacementVerifier(baseline, cell=args.cell, symbol='X',
            commanded_at_ms=time.monotonic_ns() // 1_000_000)
        recorder.record('camera_baseline', frame_id=baseline.frame_id, cells=baseline.cells,
                        source='gazebo_rendered_camera')

        def move(xyz, stage):
            recorder.record('pick_stage', stage=stage, target_m=xyz)
            start = executor.current_positions()
            validity = planner.state_validity(start)
            if not validity.valid:
                pairs = [(c.contact_body_1, c.contact_body_2) for c in validity.contacts]
                raise RuntimeError(f'pick_start_collision:{stage}:{pairs}')
            goal = planner.solve_tool_pose(start, xyz)
            executor.execute(planner.plan_joints(start, goal))
            print(stage, flush=True)

        move((SUPPLY[0], SUPPLY[1], 0.22), 'approach_supply')
        suction(True)
        move((SUPPLY[0], SUPPLY[1], 0.067), 'contact_supply')
        deadline = time.monotonic() + 3.0
        while True:
            state = gripper_state()
            if state['attached'] or time.monotonic() > deadline:
                break
        recorder.record('grasp_attempt_observed', **state)
        if not state['attached']:
            pose = planner.tool_pose(executor.current_positions())
            raise RuntimeError(f'grasp_contact_not_confirmed:{state}, tool={pose}')
        recorder.record('grasp_observed', **state)
        set_token(planner, (0.0, 0.0, 0.076), attached=True)
        # The token starts resting on its support; permit that pair only until
        # lift-off. All robot and other scene collisions remain checked.
        allow_cup_contact(planner, second='supply', enabled=True)
        move((SUPPLY[0], SUPPLY[1], 0.22), 'lift')
        allow_cup_contact(planner, second='supply', enabled=False)
        state = gripper_state()
        if not state['attached'] or state['token_xyz'][2] < 0.86:
            raise RuntimeError('token_not_lifted')
        recorder.record('token_lift_observed', **state)
        # Verify that the planner sees the carried payload, using a temporary
        # obstacle at its outer rim. No robot motion is sent with this probe.
        x, y, z = state['token_xyz']
        planner.apply_boxes([('payload_probe', (0.006, 0.006, 0.006), (x + 0.025, y, z - 0.75))])
        current = executor.current_positions()
        validity = planner.state_validity(current)
        pairs = [(c.contact_body_1, c.contact_body_2) for c in validity.contacts]
        if validity.valid or not any('token' in pair and 'payload_probe' in pair for pair in pairs):
            raise RuntimeError(f'carried_payload_not_in_collision_scene:{pairs}')
        try:
            planner.plan_joints(current, current)
        except RuntimeError as error:
            if str(error) not in ('moveit_plan_rejected:-10', 'moveit_plan_rejected:-26'):
                raise
        else:
            raise RuntimeError('planner_ignored_payload_collision')
        recorder.record('payload_collision_rejection_verified', contacts=pairs)
        remove_scene_object(planner, 'payload_probe')
        target = cell_tool_target(WORLD, args.cell, clearance=0.23)
        move(target, 'transfer')
        # Release 4 mm above the board; settling must be independently observed.
        move((target[0], target[1], 0.0735), 'lower_to_board')
        suction(False)
        time.sleep(0.3)
        state = gripper_state()
        if state['attached']:
            raise RuntimeError('release_not_confirmed')
        observed = state['token_xyz']
        set_token(planner, (observed[0], observed[1], observed[2] - 0.75))
        move(target, 'retract')
        expected = (target[0], target[1], 0.7435)
        for _ in range(3):
            state = gripper_state()
            if state['attached'] or math.dist(state['token_xyz'], expected) > 0.01:
                raise RuntimeError(f'token_placement_mismatch:{state}')
        recorder.record('simulation_placement_observed', cell=args.cell,
                         verification='gazebo_object_pose', expected_xyz=expected, **state)
        executor.execute(planner.plan_joints(executor.current_positions(), home))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            observation, frame = camera.observe()
            result = verifier.update(observation, now_ms=time.monotonic_ns() // 1_000_000)
            cv2.imwrite(str(ROOT / 'artifacts/pick-camera-after.png'), frame)
            recorder.record('camera_placement_check', result=result, cells=observation.cells,
                            valid=observation.valid, reason=observation.reason,
                            frame_id=observation.frame_id, source='gazebo_rendered_camera')
            if result == 'verified':
                recorder.record('placement_observed', cell=args.cell, symbol='X', accepted=True,
                    verification='camera', source='gazebo_rendered_camera',
                    frame_id=observation.frame_id, cells=observation.cells, confirming_frames=verifier.stable)
                break
        else:
            raise RuntimeError('camera_placement_not_confirmed')
        recorder.record('pick_place_completed', cell=args.cell)
        print('UR5e token transfer verified by rendered camera and Gazebo object state', flush=True)
        return 0
    except Exception as error:
        recorder.record('pick_place_failed', cell=args.cell, reason=str(error))
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
