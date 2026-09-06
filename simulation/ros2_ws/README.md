# ROS 2 / MoveIt 2 integration scaffold

This directory is the handoff point from the working Gazebo transport demo to a
production-shaped ROS 2 stack. It deliberately does not vendor Universal
Robots meshes. On the current machine, ROS 2 Humble plus the UR description,
MoveIt and `gz_ros2_control` packages are installed and this package has been
built with `colcon`.

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

The lightweight reference world uses Gazebo Harmonic (`gz-sim8`). The installed
Humble `gz_ros2_control` binary targets the Ignition/Gazebo 6 generation, so
the controller bridge itself is not claimed as a running Harmonic integration
yet; use the Jazzy/Harmonic target stack above for that final launch.

The installed compatibility launch is headless by design and can be verified
with `ros2 launch robotlab_ur5e_bringup ur5e_gz_ros2.launch.py`. It starts the
official UR5e through `ur_description`, creates the entity in Gazebo, and
spawns the joint-state and trajectory controllers. Add a GUI separately with
`ign gazebo` when a display is available.

The verified WSL2 command sequence is:

```bash
source /opt/ros/humble/setup.bash
source simulation/ros2_ws/install/setup.bash
ros2 launch robotlab_ur5e_bringup ur5e_gz_ros2.launch.py
```

In another terminal, confirm the control contract:

```bash
source /opt/ros/humble/setup.bash
ros2 control list_controllers
ros2 action list
```

The current validation reached `active` for both controllers and completed a
six-joint `control_msgs/action/FollowJointTrajectory` goal with
`error_code: 0`. The launch is headless so it can run reliably without an
Ogre/EGL display.

For a repeatable check instead of running the commands manually:

```bash
bash simulation/ros2_ws/scripts/ros2_smoke_test.sh
```

The smoke test now runs `scripts/guarded_motion.py`. Three synthetic pointing
observations pass the intent and transport gates, then a small joint-space
motion goes through the ROS2 action client. The executor validates the first
segment against a fresh measured joint state, checks the controller result,
and reads another joint state to verify the final target within 0.03 radians.
A second run injects 100% packet loss and must return rejection without sending
an action. Test-owned simulator processes are cleaned up as a process group.

This is an execution-adapter test: the synthetic center-cell intent authorizes
a 0.1-radian shoulder-pan movement and return, not a calibrated cell placement.
It does not establish collision avoidance or object placement. The board-cell
planner and object observer remain separate integration work. Run this script
only against the simulation launched by the smoke test.

## MoveIt planning integration

The additional `ur5e_moveit.launch.py` starts OMPL planning with the official
UR5e URDF, UR semantic groups and kinematics configuration. It exposes planning
services; motion execution is sent through `robotlab.ros2_executor` so the
measured-start safety gate and final joint observation are retained.

```bash
sudo apt-get install ros-humble-ur-moveit-config
source /opt/ros/humble/setup.bash
cd simulation/ros2_ws
colcon build --symlink-install
cd ../..
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh
```

The test loads table and board collision boxes from the Gazebo SDF, transforms
them by the simulator's 0.75 m robot-base height, plans a shoulder-pan movement
and return, and verifies both executed joint targets. It then inserts an
enclosing obstacle, requires contact evidence against that obstacle from
MoveIt's state-validity service, and requires planning rejection. JSONL
evidence is written to `artifacts/moveit-motion.jsonl`.

This checks static-scene joint-space planning. It does not yet test a Cartesian
board placement, gripper contact, a moving obstacle, or webcam integration.
Planning uses an explicitly measured start state and wall-clock service
timeouts; a shared simulation clock and a live scene sensor remain integration
work. The installed Humble MoveIt process has also shown a shutdown crash;
the test terminates its process group but does not claim clean MoveIt shutdown.

## Remaining acceptance checks

1. `joint_state_broadcaster` reports all six UR5e joints.
2. MoveIt plans a collision-free approach, descend, retract trajectory for a
   calibrated board cell.
3. The RobotLab safety gate rejects limit, speed, stale-intent, and deadline
   violations before the controller action is sent.
4. A scene observer verifies the placed token and records the result in the
   same JSONL telemetry schema used by the reference demo.
