#!/usr/bin/env bash
set -e

ROS_DISTRO_NAME="${ROS_DISTRO:-humble}"
# ROS setup files reference optional variables, so source them before enabling
# nounset. This keeps the smoke test strict without breaking a clean shell.
set +u
source "/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/install/setup.bash"
set -u
set -o pipefail

LOG_FILE="${TMPDIR:-/tmp}/robotlab-ros2-smoke.log"
ros2 launch robotlab_ur5e_bringup ur5e_gz_ros2.launch.py >"${LOG_FILE}" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -INT "${LAUNCH_PID}" 2>/dev/null || true
  wait "${LAUNCH_PID}" 2>/dev/null || true
}
trap cleanup EXIT

for _attempt in $(seq 1 40); do
  if ros2 control list_controllers 2>/dev/null | grep -q "ur5e_arm_controller.*active"; then
    break
  fi
  sleep 0.5
done

if ! ros2 control list_controllers | grep -q "ur5e_arm_controller.*active"; then
  cat "${LOG_FILE}"
  echo "UR5e trajectory controller did not become active" >&2
  exit 1
fi

ros2 action send_goal /ur5e_arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  '{trajectory: {joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_joint, wrist_1_joint, wrist_2_joint, wrist_3_joint], points: [{positions: [0.0, -1.57, 0.0, -1.57, 0.0, 0.0], time_from_start: {sec: 1}}, {positions: [0.0, -0.5574, 1.3708, -0.8133, 0.0, 0.0], time_from_start: {sec: 4}}]}}' \
  | tee "${LOG_FILE}.goal"

grep -q "Goal finished with status: SUCCEEDED" "${LOG_FILE}.goal"
echo "ROS2 UR5e smoke test passed"
