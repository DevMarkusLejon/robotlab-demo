# UR5e reference-cell demo

This replaces the toy 3-DOF arm with a six-joint UR5e-shaped reference model. It is a vertical slice of the intended RobotLab product: a human target becomes a guarded trajectory, Gazebo executes it, and JSONL telemetry records what happened.

The exact reference constants used for the next official-model integration are
captured in [`ur5e_reference.json`](ur5e_reference.json). The current SDF keeps
lightweight geometry for fast local iteration; it does not pretend to be the
licensed production mesh.

Once the ROS2 packages are sourced in WSL2, the official UR meshes and links
can be generated locally with:

```bash
source /opt/ros/humble/setup.bash
python3 simulation/ur5e/generate_official_sdf.py
gz sim -v 2 -r artifacts/ur5e-official-world.sdf
```

The generated artifact uses the installed `ur_description` package and leaves
control to the ROS2 scaffold. This keeps the repository small while making the
exact model reproducible on a ROS host. Mesh URIs are resolved to the local
ROS installation at generation time, so no Gazebo resource-path environment
variable is needed for the generated wrapper on that host.

Open `dashboard.html` in a browser for the accompanying pitch surface. It makes the execution stages visible: intent, transport, safety, trajectory, and observer confirmation.

## Run

Use WSL2 Ubuntu 22.04. ROS 2 is not required for this first vertical slice; the `gz topic` transport is intentionally kept behind a small executor seam so it can be replaced by `gz_ros2_control` and MoveIt 2 when the hardware and ROS distribution are confirmed.

```bash
cd "/mnt/c/Users/User/Documents/ChatGPT/Björn"
gz sim -v 2 -r simulation/ur5e/world.sdf
```

In a second WSL terminal:

```bash
cd "/mnt/c/Users/User/Documents/ChatGPT/Björn"
python3 simulation/ur5e/ur5e_demo.py --cell 4
```

Run the short multi-target demo with:

```bash
python3 simulation/ur5e/ur5e_demo.py
```

To exercise the complete guarded path with a deterministic pointing intent,
run the shared-autonomy driver. It feeds a stable target through perception,
transport and safety before publishing the UR5e trajectory:

```bash
python3 simulation/ur5e/shared_autonomy_demo.py --cell 4 --settle 1.2
```

Transport conditions can be exercised without changing the robot scene:

```bash
python3 simulation/ur5e/ur5e_demo.py --latency-ms 180 --jitter-ms 40 --deadline-ms 500
python3 simulation/ur5e/ur5e_demo.py --drop-rate 1.0
```

The first command records the modeled delivery latency before a command is
published. The second demonstrates a fail-closed packet-loss rejection. Both
outcomes are written to the JSONL event stream.

The driver checks joint limits, finite values, monotonic timestamps, and maximum joint speed before publishing anything. It records `demo_started`, `trajectory_checked`, `trajectory_point`, `trajectory_commands_sent`, and `demo_completed` in `artifacts/ur5e-events.jsonl`. This transport-only driver has no motion or placement observer: completion means the commands were sent. Use the ROS2 path for measured motion verification; placement still needs camera or gripper evidence. Older logs containing `verification="simulated_scene_observer"` are placeholders and are not placement evidence.

`robotlab.intent.IntentGate`, `robotlab.network.NetworkSimulator`, and `robotlab.pipeline.SharedAutonomyPipeline` are dependency-free seams for the camera, unreliable transport, and execution adapter. They are covered by tests and can be connected to the existing MediaPipe webcam loop without changing the game rules.

The ROS 2 handoff is captured in [`simulation/ros2_ws`](../ros2_ws). It pins
the six-joint controller contract while leaving official UR meshes and the
final launch topology to the target ROS distribution.

For a physical overhead camera, save four image points in the order
top-left, top-right, bottom-right, bottom-left. The checked-in
[`calibration.example.json`](calibration.example.json) shows the format;
`robotlab.calibration.BoardCalibration.from_json` maps fingertip pixels through
the resulting perspective transform before the intent gate sees them.

## Product path

The next ROS 2 integration should use the official UR description for `ur5e` and the same joint names, then connect the model to `gz_ros2_control` and a `JointTrajectoryController`. ROS 2 Jazzy's recommended Gazebo release is Harmonic, and `gz_ros2_control` exists specifically to control simulated robots through `ros2_control` ([ROS 2 release guidance](https://docs.ros.org/en/iron/Releases/Release-Jazzy-Jalisco.html), [gz_ros2_control](https://docs.ros.org/en/ros2_packages/jazzy/api/gz_ros2_control/index.html)). The official Universal Robots description contains the UR5e kinematics, limits, physical parameters, and meshes; it is the right source to use once its licensing and packaging are approved ([repository](https://github.com/UniversalRobots/Universal_Robots_ROS2_Description)). MoveIt 2 can execute the same controller contract in simulation and against real hardware ([trajectory execution guide](https://moveit.picknik.ai/main/doc/how_to_guides/moveit_launch_files/moveit_launch_files_tutorial.html)).
