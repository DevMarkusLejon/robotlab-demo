# UR5e reference-cell demo

This replaces the toy 3-DOF arm with a six-joint UR5e-shaped reference model. It is a vertical slice of the intended RobotLab product: a human target becomes a guarded trajectory, Gazebo executes it, and JSONL telemetry records what happened.

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

The driver checks joint limits, finite values, monotonic timestamps, and maximum joint speed before publishing anything. It records `demo_started`, `trajectory_checked`, `trajectory_point`, `placement_verified`, and `demo_completed` in `artifacts/ur5e-events.jsonl`. The current placement verification is a simulation observer seam; a real version must consume camera or gripper feedback before claiming success.

`robotlab.intent.IntentGate`, `robotlab.network.NetworkSimulator`, and `robotlab.pipeline.SharedAutonomyPipeline` are dependency-free seams for the camera, unreliable transport, and execution adapter. They are covered by tests and can be connected to the existing MediaPipe webcam loop without changing the game rules.

## Product path

The next ROS 2 integration should use the official UR description for `ur5e` and the same joint names, then connect the model to `gz_ros2_control` and a `JointTrajectoryController`. ROS 2 Jazzy's recommended Gazebo release is Harmonic, and `gz_ros2_control` exists specifically to control simulated robots through `ros2_control` ([ROS 2 release guidance](https://docs.ros.org/en/iron/Releases/Release-Jazzy-Jalisco.html), [gz_ros2_control](https://docs.ros.org/en/ros2_packages/jazzy/api/gz_ros2_control/index.html)). The official Universal Robots description contains the UR5e kinematics, limits, physical parameters, and meshes; it is the right source to use once its licensing and packaging are approved ([repository](https://github.com/UniversalRobots/Universal_Robots_ROS2_Description)). MoveIt 2 can execute the same controller contract in simulation and against real hardware ([trajectory execution guide](https://moveit.picknik.ai/main/doc/how_to_guides/moveit_launch_files/moveit_launch_files_tutorial.html)).
