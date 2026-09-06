# ROS 2 / MoveIt 2 integration scaffold

This directory is the handoff point from the working Gazebo transport demo to a
production-shaped ROS 2 stack. It deliberately does not vendor Universal
Robots meshes or claim that ROS 2 is installed on the current Windows/WSL
machine.

## Target stack

- Ubuntu 24.04 + ROS 2 Jazzy
- Gazebo Harmonic
- `ur_description` from Universal Robots for the official UR5e model
- `gz_ros2_control` for the Gazebo-to-`ros2_control` bridge
- `joint_trajectory_controller` for the six-joint command contract
- MoveIt 2 for collision-aware planning and execution

The current `simulation/ur5e/world.sdf` remains useful as a lightweight
reference world. The next integration should spawn the official `ur5e` xacro
inside that world, attach the controller configuration in `config/`, and route
the `SharedAutonomyPipeline` trajectory through a MoveIt action client.

## Planned build on a ROS 2 host

```bash
source /opt/ros/jazzy/setup.bash
cd simulation/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

The package in `src/robotlab_ur5e_bringup` contains the controller names and
joint order used by the Python safety gate, plus the matching MoveIt
`FollowJointTrajectory` contract. It is intentionally a scaffold until the
exact URDF, world spawn arguments, and hardware namespace are agreed.

## Acceptance checks for the real bridge

1. `joint_state_broadcaster` reports all six UR5e joints.
2. MoveIt plans a collision-free approach, descend, retract trajectory for a
   calibrated board cell.
3. The RobotLab safety gate rejects limit, speed, stale-intent, and deadline
   violations before the controller action is sent.
4. A scene observer verifies the placed token and records the result in the
   same JSONL telemetry schema used by the reference demo.
