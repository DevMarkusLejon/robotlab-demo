# RobotLab Gazebo simulation

This is a visual and kinematics prototype for the RobotLab idea: a 3×3 board, a simple 3-DOF arm, and a small sequence driver. It is deliberately separate from hardware drivers. The arm commands go to Gazebo topics, so the same planning layer can later be connected to a real controller after calibration and safety work.

## Run it

Gazebo is not installed in the Windows workspace by default. The most reliable route is **WSL2 with Ubuntu** (or a native Linux machine) using Gazebo Harmonic:

```bash
sudo apt-get update
sudo apt-get install -y gz-harmonic
cd /mnt/c/Users/User/Documents/ChatGPT/Björn
gz sim -v 4 simulation/gazebo/world.sdf
```

When the window is open, run the motion demo from a second WSL terminal:

```bash
cd /mnt/c/Users/User/Documents/ChatGPT/Björn
python3 simulation/gazebo/play_demo.py
```

To move to one cell (`0` is top-left and `8` is bottom-right):

```bash
python3 simulation/gazebo/play_demo.py --cell 4
```

The driver publishes `gz.msgs.Double` position commands to `/robotlab/arm/{base,shoulder,elbow}/cmd`. It uses a small analytic two-link IK calculation and an approach/descend/retract sequence. The model is intentionally simple: it demonstrates scene layout, joint control, and a path from board coordinates to arm targets. It is not a dynamics-accurate model of a production arm.

## Why Gazebo here?

The webcam example answers “which square did the person indicate?” This simulation answers the next engineering question: “can a planned move be expressed as safe, inspectable robot motion?” It lets us tune board geometry, reachability, timing, and the command interface before choosing a real robot, gripper, or ROS 2 integration.

The world uses Gazebo's built-in physics, scene broadcaster, joint state publisher, and joint position controller systems. See the [Gazebo Harmonic SDF world guide](https://gazebosim.org/docs/harmonic/sdf_worlds/) and [JointPositionController documentation](https://gazebosim.org/api/sim/9/jointcontrollers.html).
