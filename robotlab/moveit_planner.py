"""MoveIt service adapter with explicit measured start and collision scene."""
import xml.etree.ElementTree as ET
import math

from .safety import JointPoint, UR5E_JOINTS


def cell_tool_target(path, cell, clearance=0.15):
    """Tool0 hover point above an SDF board cell, expressed in base_link."""
    if type(cell) is not int or not 0 <= cell < 9:
        raise ValueError('cell must be in [0, 8]')
    if not math.isfinite(clearance) or clearance < 0.08:
        raise ValueError('tool hover clearance must be at least 0.08 m')
    board = next((item for item in world_boxes(path) if item[0] == 'board'), None)
    if board is None:
        raise ValueError('board missing from world')
    _, size, center = board
    row, column = divmod(cell, 3)
    return (center[0] + (column - 1) * size[0] / 3,
            center[1] + (row - 1) * size[1] / 3,
            center[2] + size[2] / 2 + clearance)


def world_boxes(path, base_height=0.75):
    """Translate the demo's axis-aligned SDF boxes into the robot base frame."""
    boxes = []
    for model in ET.parse(path).getroot().findall('./world/model'):
        box = model.find('./link/collision/geometry/box/size')
        if box is None:
            continue
        pose = [float(x) for x in model.findtext('pose', '0 0 0 0 0 0').split()]
        if len(pose) != 6 or any(pose[3:]):
            raise ValueError('Only axis-aligned model poses are supported')
        boxes.append((model.attrib['name'], tuple(float(x) for x in box.text.split()),
                      (pose[0], pose[1], pose[2] - base_height)))
    boxes.append(('ground', (20.0, 20.0, 0.1), (0.0, 0.0, -base_height - 0.05)))
    return boxes


class MoveItPlanner:
    def __init__(self, node):
        self.node = node

    def call(self, service_type, name, request, timeout=15.0):
        import rclpy
        client = self.node.create_client(service_type, name)
        try:
            if not client.wait_for_service(timeout_sec=timeout):
                raise RuntimeError(f'service_unavailable:{name}')
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
            if not future.done():
                raise RuntimeError(f'service_timeout:{name}')
            return future.result()
        finally:
            self.node.destroy_client(client)

    def apply_boxes(self, boxes):
        from moveit_msgs.srv import ApplyPlanningScene
        from moveit_msgs.msg import CollisionObject
        from shape_msgs.msg import SolidPrimitive
        from geometry_msgs.msg import Pose
        request = ApplyPlanningScene.Request()
        request.scene.is_diff = True
        request.scene.robot_state.is_diff = True
        for name, size, position in boxes:
            obj = CollisionObject()
            obj.id = name
            obj.header.frame_id = 'base_link'
            obj.operation = CollisionObject.ADD
            primitive = SolidPrimitive(type=SolidPrimitive.BOX, dimensions=list(size))
            pose = Pose()
            pose.orientation.w = 1.0
            pose.position.x, pose.position.y, pose.position.z = position
            obj.primitives = [primitive]
            obj.primitive_poses = [pose]
            request.scene.world.collision_objects.append(obj)
        if not self.call(ApplyPlanningScene, '/apply_planning_scene', request).success:
            raise RuntimeError('planning_scene_rejected')

    def plan_joints(self, start, target):
        from moveit_msgs.srv import GetMotionPlan
        from moveit_msgs.msg import Constraints, JointConstraint
        request = GetMotionPlan.Request()
        motion = request.motion_plan_request
        motion.group_name = 'ur_manipulator'
        motion.allowed_planning_time = 5.0
        motion.num_planning_attempts = 1
        motion.max_velocity_scaling_factor = 0.1
        motion.max_acceleration_scaling_factor = 0.1
        motion.start_state.joint_state.name = list(UR5E_JOINTS)
        motion.start_state.joint_state.position = list(start)
        goal = Constraints()
        for joint, value in zip(UR5E_JOINTS, target):
            goal.joint_constraints.append(JointConstraint(joint_name=joint, position=float(value),
                tolerance_above=0.001, tolerance_below=0.001, weight=1.0))
        motion.goal_constraints = [goal]
        response = self.call(GetMotionPlan, '/plan_kinematic_path', request).motion_plan_response
        if response.error_code.val != 1:
            raise RuntimeError(f'moveit_plan_rejected:{response.error_code.val}')
        trajectory = response.trajectory.joint_trajectory
        order = [trajectory.joint_names.index(joint) for joint in UR5E_JOINTS]
        points = []
        for item in trajectory.points:
            seconds = item.time_from_start.sec + item.time_from_start.nanosec / 1e9
            if seconds == 0:
                if max(abs(item.positions[i] - value) for i, value in zip(order, start)) > 0.01:
                    raise RuntimeError('planner_changed_start_state')
                continue
            points.append(JointPoint(seconds, tuple(item.positions[i] for i in order)))
        if not points:
            raise RuntimeError('empty_moveit_plan')
        return tuple(points)

    def state_validity(self, positions):
        from moveit_msgs.srv import GetStateValidity
        request = GetStateValidity.Request()
        request.group_name = 'ur_manipulator'
        request.robot_state.joint_state.name = list(UR5E_JOINTS)
        request.robot_state.joint_state.position = list(positions)
        return self.call(GetStateValidity, '/check_state_validity', request)

    def tool_pose(self, positions):
        """Compute tool pose from measured joints (not an independent camera)."""
        from moveit_msgs.srv import GetPositionFK
        request = GetPositionFK.Request()
        request.header.frame_id = 'base_link'
        request.fk_link_names = ['tool0']
        request.robot_state.joint_state.name = list(UR5E_JOINTS)
        request.robot_state.joint_state.position = list(positions)
        result = self.call(GetPositionFK, '/compute_fk', request)
        if result.error_code.val != 1 or len(result.pose_stamped) != 1:
            raise RuntimeError('forward_kinematics_failed')
        return result.pose_stamped[0].pose

    def solve_tool_pose(self, seed, xyz):
        from moveit_msgs.srv import GetPositionIK
        from moveit_msgs.msg import JointConstraint
        from .safety import UR5E_LIMITS
        request = GetPositionIK.Request()
        ik = request.ik_request
        ik.group_name = 'ur_manipulator'
        ik.ik_link_name = 'tool0'
        ik.avoid_collisions = True
        ik.timeout.sec = 3
        ik.robot_state.joint_state.name = list(UR5E_JOINTS)
        ik.robot_state.joint_state.position = list(seed)
        ik.pose_stamped.header.frame_id = 'base_link'
        pose = ik.pose_stamped.pose
        pose.position.x, pose.position.y, pose.position.z = xyz
        pose.orientation.x = 1.0
        pose.orientation.w = 0.0
        for joint, (low, high) in zip(UR5E_JOINTS, UR5E_LIMITS):
            ik.constraints.joint_constraints.append(JointConstraint(joint_name=joint,
                position=(low + high) / 2, tolerance_above=(high - low) / 2,
                tolerance_below=(high - low) / 2, weight=1.0))
        result = self.call(GetPositionIK, '/compute_ik', request)
        if result.error_code.val != 1:
            raise RuntimeError(f'ik_rejected:{result.error_code.val}')
        values = dict(zip(result.solution.joint_state.name, result.solution.joint_state.position))
        # Equivalent wrist turns can otherwise add an unnecessary full rotation.
        nearest = []
        for joint, current, (low, high) in zip(UR5E_JOINTS, seed, UR5E_LIMITS):
            choices = [values[joint] + k * 2 * math.pi for k in range(-2, 3)
                       if low <= values[joint] + k * 2 * math.pi <= high]
            if not choices:
                raise RuntimeError('ik_outside_safety_limits')
            nearest.append(min(choices, key=lambda value: abs(value - current)))
        return tuple(nearest)
