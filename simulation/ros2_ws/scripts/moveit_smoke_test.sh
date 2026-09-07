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
if [ "${1:-}" = "--live" ]; then
  python3 "${SCRIPT_DIR}/live_robot.py"
elif [ "${1:-}" = "--cell" ]; then
  timeout 120 python3 "${SCRIPT_DIR}/cell_motion.py" --cell "${2:-4}"
elif [ "${1:-}" = "--check-cells" ]; then
  timeout 120 python3 "${SCRIPT_DIR}/cell_motion.py" --check-cells
elif [ "${1:-}" = "--all-cells" ]; then
  timeout 240 python3 "${SCRIPT_DIR}/cell_motion.py" --all-cells
else
  timeout 90 python3 "${SCRIPT_DIR}/planned_motion.py"
fi
