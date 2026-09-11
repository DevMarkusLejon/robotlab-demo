# Contact-gated suction reference

## Multi-token game (September 2026)

The desktop launcher now runs `--game`, with five red and four blue tokens.
`robotlab.token_supply.SimulatedDispenser` creates each additional token once
at the supply pedestal. It does not relocate existing objects. This models a
dispenser, not a physical nine-position rack; real feed hardware is undecided.

The `/robotlab/gripper/select` StringMsg topic selects `token` or `token_1` through
`token_8`. Selection is applied only when suction is disabled and no joint is
attached, and is acknowledged as `token_name` in the state message. Each placed
token remains in the physics world and MoveIt scene. Cup contact permissions
are removed after retracting from each placed token. All new moves require a
camera baseline matching the entire previously confirmed board.

Build the updated plugin with `cmake --build simulation/gripper/build -j2`
before using the new launcher. The single-token commands below remain available
for isolated placement tests. Historical validation dates below describe those
earlier tests; see `docs/implementation-status.md` for current results.

This Gazebo Fortress system implements an **idealized suction attachment**.
It requires the cup collision to contact the configured token link for three
simulation updates before creating a detachable fixed joint. Disabling suction
removes that joint. It starts disabled and cannot attach an object at a distance.
There is no model of vacuum pressure, seal quality, payload limits, or slip.

The plugin uses Gazebo's [detachable joint component](https://gazebosim.org/api/gazebo/6/detachablejoints.html).
The plugin enables contact reporting directly on the cup link's collision
entities, avoiding URDF conversion names. Evidence comes from the physics-filled collision component used by
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
The launch files accept a `description_file` override so the
same wrapper is used for physics and planning.

After building the ROS workspace, verify a cell hover with the cup mounted:

```bash
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --gripper-check
```

Validated: contact attachment/carry/release in the fixture, and a center-cell
UR5e hover plus return with the mounted cup (2.22 mm tool error from simulated
joint feedback). The integrated token-transfer test below adds robot-driven
pickup and placement. Camera confirmation remains separate work.

## Robot-driven pickup and placement

```bash
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh --pick-place 4
```

The runner generates an alternate scene containing a supply pedestal and one
dynamic token. UR5e approaches the supply, establishes cup contact, lifts the
token, transfers it to the selected cell, lowers, releases, retracts and returns
home. No `set_pose` command moves the token during this integrated test.

MoveIt receives the token as an attached collision body during carry; explicit
measured start states preserve that attachment. Only token/cup contact is
generally permitted. Token/supply contact is additionally permitted during
lift-off, then disabled. A temporary planning-only obstacle at the payload rim
must produce a token collision and planning rejection; it is removed before
transport. Scene changes are read back to verify attachment state.

The official URDF's zero-thickness floor at base height is removed in both
physics and planning: it would intersect the worktable tokens because the
robot base is elevated 0.75 m. Robot collisions and the world's ground, table,
board and supply geometry remain present.

On 2026-09-07 the full center-cell sequence passed with carried-payload collision
rejection. Gazebo reported the released token at approximately
`[0.449463, -0.000143, 0.743500]` m versus `[0.450000, 0, 0.743500]` m expected.
Three successive object-state samples must be within 10 mm and detached before
placement is recorded. This check is simulation ground truth, not physical
robot evidence. The sequence now additionally requires three rendered overhead
camera frames showing the requested cell change after the robot returns home.
Camera events are labeled `source=gazebo_rendered_camera`; before/after PNGs
are saved in `artifacts/`. Camera confirmation passed for center cell 4 and
corner cell 0 on 2026-09-07. Other carried-token placement cells remain unverified.

Logs remain under `artifacts/` (`pick-place.jsonl`, `robotlab-pick.sdf`, and
`moveit.*.log`). `--live-pick-place` connects hand intent to this one-token
pickup experiment and records to `live-robot.jsonl`. The synthetic Windows
client test passed; manual pointing remains to be verified. The webcam UI
shows the live simulated board camera beside the hand view.

The command topic is `/robotlab/gripper/enable` (`ignition.msgs.Boolean`).
`/robotlab/gripper/state` carries a JSON string containing attachment state,
current contact count, contact updates at the last attachment and observed
token position. A reported fixed-joint attachment is not a physical force or
seal measurement.
