"""MoveIt collision-scene updates for a carried cylindrical demo token."""
from .moveit_planner import MoveItPlanner


def allow_cup_contact(planner: MoveItPlanner, first='token', second='vacuum_cup', *, enabled=True):
    from moveit_msgs.srv import GetPlanningScene, ApplyPlanningScene
    from moveit_msgs.msg import PlanningSceneComponents, AllowedCollisionEntry
    query = GetPlanningScene.Request()
    query.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
    matrix = planner.call(GetPlanningScene, '/get_planning_scene', query).scene.allowed_collision_matrix
    for name in (first, second):
        if name not in matrix.entry_names:
            matrix.entry_names.append(name)
            for row in matrix.entry_values:
                row.enabled.append(False)
            matrix.entry_values.append(AllowedCollisionEntry(enabled=[False] * len(matrix.entry_names)))
    a, b = (matrix.entry_names.index(name) for name in (first, second))
    matrix.entry_values[a].enabled[b] = enabled
    matrix.entry_values[b].enabled[a] = enabled
    request = ApplyPlanningScene.Request()
    request.scene.is_diff = True
    request.scene.robot_state.is_diff = True
    request.scene.allowed_collision_matrix = matrix
    if not planner.call(ApplyPlanningScene, '/apply_planning_scene', request).success:
        raise RuntimeError('cup_contact_permission_failed')


def set_token(planner: MoveItPlanner, position, *, attached=False):
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from moveit_msgs.msg import CollisionObject, AttachedCollisionObject, PlanningSceneComponents
    from shape_msgs.msg import SolidPrimitive
    from geometry_msgs.msg import Pose
    obj = CollisionObject()
    obj.id = 'token'
    obj.header.frame_id = 'vacuum_cup' if attached else 'base_link'
    obj.operation = CollisionObject.ADD
    obj.primitives = [SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[0.012, 0.03])]
    pose = Pose()
    pose.orientation.w = 1.0
    pose.position.x, pose.position.y, pose.position.z = position
    obj.primitive_poses = [pose]
    request = ApplyPlanningScene.Request()
    request.scene.is_diff = True
    request.scene.robot_state.is_diff = True
    body = AttachedCollisionObject()
    body.link_name = 'vacuum_cup'
    if attached:
        # MoveIt removes the matching world object as part of attachment.
        body.object = obj
        body.touch_links = ['vacuum_cup']
    else:
        body.object = CollisionObject(id='token', operation=CollisionObject.REMOVE)
        request.scene.world.collision_objects = [obj]
    request.scene.robot_state.attached_collision_objects = [body]
    if not planner.call(ApplyPlanningScene, '/apply_planning_scene', request).success:
        raise RuntimeError('token_scene_update_failed')
    query = GetPlanningScene.Request()
    query.components.components = (PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS |
                                   PlanningSceneComponents.WORLD_OBJECT_NAMES)
    scene = planner.call(GetPlanningScene, '/get_planning_scene', query).scene
    carried = any(body.object.id == 'token' and body.link_name == 'vacuum_cup'
                  for body in scene.robot_state.attached_collision_objects)
    in_world = any(body.id == 'token' for body in scene.world.collision_objects)
    if carried != attached or in_world == attached:
        raise RuntimeError('token_scene_readback_mismatch')


def remove_scene_object(planner, name):
    from moveit_msgs.srv import ApplyPlanningScene
    from moveit_msgs.msg import CollisionObject
    request = ApplyPlanningScene.Request()
    request.scene.is_diff = True
    request.scene.robot_state.is_diff = True
    request.scene.world.collision_objects = [CollisionObject(id=name, operation=CollisionObject.REMOVE)]
    if not planner.call(ApplyPlanningScene, '/apply_planning_scene', request).success:
        raise RuntimeError('scene_object_removal_failed')
