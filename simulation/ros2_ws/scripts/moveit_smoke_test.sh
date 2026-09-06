#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../install/setup.bash"
set -uo pipefail
LOG_FILE="$(mktemp /tmp/robotlab-moveit.XXXXXX.log)"
setsid ros2 launch robotlab_ur5e_bringup ur5e_moveit.launch.py >"${LOG_FILE}" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -INT -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 2
  kill -TERM -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 1
  kill -KILL -- "-${LAUNCH_PID}" 2>/dev/null || true
  wait "${LAUNCH_PID}" 2>/dev/null || true
  echo "MoveIt log: ${LOG_FILE}"
}
trap cleanup EXIT
timeout 90 python3 "${SCRIPT_DIR}/planned_motion.py"
