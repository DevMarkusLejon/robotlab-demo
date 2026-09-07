# ROS 2 / MoveIt 2 UR5e simulation

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

The ROS2 simulation spawns the official `ur5e` xacro and uses the controller
configuration in `config/`. The older `simulation/ur5e/world.sdf` remains a
separate lightweight reference world with simplified geometry.

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
`FollowJointTrajectory` contract. Physical-hardware namespaces and calibration
still need to be configured when the real robot is available.

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

This checks static-scene joint-space planning. The cell-hover test below adds
Cartesian tool goals. Neither test verifies gripper contact, a moving obstacle,
or webcam integration.
Planning uses an explicitly measured start state and wall-clock service
timeouts; a shared simulation clock and a live scene sensor remain integration
work. The installed Humble MoveIt process has also shown a shutdown crash;
the test terminates its process group but does not claim clean MoveIt shutdown.

## Tool hover above board cells

`cell_motion.py` maps each of the nine cells to a pose above the actual SDF
board, requests collision-aware inverse kinematics for downward-facing `tool0`,
and executes an OMPL plan through the measured-start safety gate. It checks the
tool position and orientation using forward kinematics of the observed joint
positions, then returns home. This verifies a hover, not a placed token.

```bash
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --cell 4
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --check-cells
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --all-cells
```

The first command executes one cell. The second plans all nine without moving.
The third executes all nine and checks each observed tool pose. Evidence is
appended to `artifacts/cell-motion.jsonl`. Acceptance limits are 10 mm position
error and 0.05 rad orientation error. The hover is 150 mm above the board's top
surface; no gripper or tool extension is modeled yet.

The ROS2 board is now 450 mm square, centered 450 mm ahead of the robot base.
The original 620 mm board at x=280 mm had three cells outside the valid
downward-tool workspace under the configured joint limits. The new layout is
shared by the collision scene and simulator through the SDF. It is a simulation
layout, not a measured calibration of the physical RobotLab table.

Validation on 2026-09-06: all nine cell plans passed collision and joint-speed
checks, followed by an executed nine-cell sweep and return home. Observed
position errors ranged from 1.23 to 1.86 mm using simulated joint feedback and
the official UR5e forward kinematics. These are simulation measurements, not
physical robot accuracy measurements.

## Live Windows webcam to UR5e

Start the local receiver and simulator in WSL from the repository root:

```bash
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --live
```

After `UR5e webcam receiver ready`, run this in a Windows terminal at the same
repository root (the current Windows Python already has the webcam packages):

```powershell
python -m robotlab.webcam_robot
```

Point your index finger into the camera's overlaid grid and hold for roughly
1.2 seconds. The selected cell becomes a downward-facing tool hover in Gazebo,
followed by return to the starting pose. Move your hand out of the grid after
the move finishes before selecting again. Q/Esc closes the webcam window;
an already accepted simulated motion continues. Stop the WSL receiver with
Ctrl+C after the motion has finished.

The bridge only listens on `127.0.0.1:8766`. Images stay in the Windows camera
process; only normalized hand observations are sent. The receiver checks
confidence, gesture, frame freshness, increasing sequence numbers and a server
run ID. It accepts one motion at a time and does not queue gestures while busy.
The client estimates the Windows/WSL clock offset; the receiver allows up to
50 ms estimation error toward the future and rejects frames older than 500 ms.

For a repeatable integration test, use a freshly started live receiver and run
`python simulation/ros2_ws/scripts/live_bridge_smoke.py` from Windows. This
sends **synthetic** observations, verifies completion through the status API,
and checks that a held gesture is rejected until release. On 2026-09-06 this
test passed against Gazebo; the separate real-camera check acquired an image
and ran MediaPipe successfully, with no hand in view. A manual pointing trial
has therefore not yet been verified. Motion evidence is recorded in
`artifacts/live-robot.jsonl`.

## Independent camera placement observer

`robotlab.board_observer` detects matte round red (X) and blue (O) tokens in a
four-corner calibrated camera view. A placement requires an initially empty
target, a fresh baseline, and three distinct fresh frames showing exactly the
expected board change. Wrong cells, extra changes, ambiguous shapes, tokens
across grid boundaries, duplicate frames and stale observations cannot confirm
placement. The interactive runner also rejects frames containing a detected
hand.

Save measured camera corners as `corners_px` in top-left, top-right,
bottom-right, bottom-left order, as described by the calibration example. Then
run from Windows (close the hand-control camera window first):

```powershell
python -m robotlab.observe_board --calibration YOUR_CALIBRATION.json --cell 4 --symbol X
```

Press B with the intended cell empty and hands out of view. Manually place a
red round token in the center cell, then remove your hand. Verified observations
go to `artifacts/board-observer.jsonl`. This is a separate manual perception
experiment, not an automated robot pick/place. The detector has been tested on
synthetic token images and invalid/replayed observations; physical token images
and a robot-driven placement have not yet been validated. Stable lighting and
camera position are assumed; calibration drift is not automatically detected.

The lightweight demo no longer emits placeholder placement success. Metrics
ignore its old `simulated_scene_observer` events, and return an unavailable
placement rate when no camera observation exists. The static pitch dashboard
is explicitly labeled as an illustrative mockup.

## Remaining acceptance checks

The optional [suction reference](../gripper/README.md) now has a tested
contact/carry/release physics fixture and an official UR5e wrapper with the
cup included in collision geometry. `--gripper-check` verifies the mounted-cup
hover after the plugin is built. `--pick-place 4` additionally runs robot-driven
pickup, carried-payload collision rejection, and center-cell placement verified
from Gazebo token position. Camera confirmation and live-webcam selection of
pick/place remain to be connected.

1. `joint_state_broadcaster` reports all six UR5e joints.
2. MoveIt plans a collision-free approach, descend, retract trajectory for a
   calibrated board cell.
3. The RobotLab safety gate rejects limit, speed, stale-intent, and deadline
   violations before the controller action is sent.
4. A scene observer verifies the placed token and records the result in the
   same JSONL telemetry schema used by the reference demo.
