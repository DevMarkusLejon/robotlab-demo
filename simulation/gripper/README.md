# Contact-gated suction reference

This Gazebo Fortress system implements an **idealized suction attachment**.
It requires the cup collision to contact the configured token link for three
simulation updates before creating a detachable fixed joint. Disabling suction
removes that joint. It starts disabled and cannot attach an object at a distance.
There is no model of vacuum pressure, seal quality, payload limits, or slip.

The plugin uses Gazebo's [detachable joint component](https://gazebosim.org/api/gazebo/6/detachablejoints.html).
Contact evidence comes from the physics-filled collision component used by
Gazebo's [Contact system](https://github.com/gazebosim/gz-sim/blob/ign-gazebo6/src/systems/contact/Contact.cc).

## Build and physics test

Run in the configured Ubuntu-22.04 WSL distribution at the repository root:

```bash
cmake -S simulation/gripper -B simulation/gripper/build
cmake --build simulation/gripper/build -j2
python3 simulation/gripper/smoke_test.py
```

The build requires the installed `libignition-gazebo6-dev` headers and compiler.
The test launches a separate transport partition, confirms distant attachment
is rejected, brings a token into contact, moves and inverts the fixture with
the token attached, and releases it. Measured token position must show that it
was carried to height and then fell to the ground. The test moves its fixture
and token using `set_pose` solely to isolate the gripper from arm planning;
this is not evidence of a UR5e pick/place sequence.

Evidence and simulator output are saved in ignored `build/evidence.json` and
`build/smoke.log`. Test processes are stopped on success or failure.

## UR5e integration

`simulation/ros2_ws/src/robotlab_ur5e_bringup/urdf/ur5e_vacuum.urdf.xacro`
extends the official UR5e with a 50 g cup fixed to `tool0`. The cylinder extends
70 mm along the tool axis and is included in both Gazebo and MoveIt's geometry.
Its contact collision name is the name produced by the installed libsdformat
URDF converter. The launch files accept a `description_file` override so the
same wrapper is used for physics and planning.

After building the ROS workspace, verify a cell hover with the cup mounted:

```bash
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --gripper-check
```

Validated: contact attachment/carry/release in the fixture, and a center-cell
UR5e hover plus return with the mounted cup (2.22 mm tool error from simulated
joint feedback). The UR5e test world has no supply token yet; the robot-driven
approach, contact, grasp, lift, placement and camera confirmation chain remains
to be connected and tested.

The command topic is `/robotlab/gripper/enable` (`ignition.msgs.Boolean`).
`/robotlab/gripper/state` carries a JSON string containing attachment state,
current contact count, contact updates at the last attachment and observed
token position. A reported fixed-joint attachment is not a physical force or
seal measurement.
