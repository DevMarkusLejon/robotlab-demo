#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../install/setup.bash"
set -uo pipefail
mkdir -p "${SCRIPT_DIR}/../../../artifacts"
LOG_FILE="$(mktemp "${SCRIPT_DIR}/../../../artifacts/moveit.XXXXXX.log")"
LAUNCH_EXTRA=()
FAULT_ARGS=()
if [ "${1:-}" = "--live-pick-place" ] && [ -n "${2:-}" ]; then
  case "$2" in camera_unavailable|grasp_missing) FAULT_ARGS=(--test-fault "$2") ;; *) exit 2 ;; esac
fi
if [ "${1:-}" = "--gripper-check" ] || [ "${1:-}" = "--pick-place" ] || [ "${1:-}" = "--live-pick-place" ] || [ "${1:-}" = "--game" ]; then
  export IGN_GAZEBO_SYSTEM_PLUGIN_PATH="$(realpath "${SCRIPT_DIR}/../../gripper/build")"
  LAUNCH_EXTRA+=("description_file:=$(realpath "${SCRIPT_DIR}/../src/robotlab_ur5e_bringup/urdf/ur5e_vacuum.urdf.xacro")")
fi
if [ "${1:-}" = "--pick-place" ] || [ "${1:-}" = "--live-pick-place" ] || [ "${1:-}" = "--game" ]; then
  python3 "${SCRIPT_DIR}/pick_place.py" --prepare-world
  LAUNCH_EXTRA+=("world_file:=$(realpath "${SCRIPT_DIR}/../../../artifacts/robotlab-pick.sdf")")
fi
setsid ros2 launch robotlab_ur5e_bringup ur5e_moveit.launch.py "${LAUNCH_EXTRA[@]}" >"${LOG_FILE}" 2>&1 &
LAUNCH_PID=$!
WORKER_PID=""
cleanup() {
  if [ -n "$WORKER_PID" ]; then
    kill -TERM -- "-${WORKER_PID}" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
  kill -INT -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 2
  kill -TERM -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 1
  kill -KILL -- "-${LAUNCH_PID}" 2>/dev/null || true
  wait "${LAUNCH_PID}" 2>/dev/null || true
  echo "MoveIt log: ${LOG_FILE}"
}
trap cleanup EXIT
trap 'exit 0' INT TERM
if [ "${1:-}" = "--game" ]; then
  setsid python3 "${SCRIPT_DIR}/live_robot.py" --game &
  WORKER_PID=$!
  wait "$WORKER_PID"
elif [ "${1:-}" = "--pick-place" ]; then
  timeout 240 python3 "${SCRIPT_DIR}/pick_place.py" --cell "${2:-4}"
elif [ "${1:-}" = "--gripper-check" ]; then
  timeout 120 python3 "${SCRIPT_DIR}/cell_motion.py" --cell 4
elif [ "${1:-}" = "--live" ]; then
  setsid python3 "${SCRIPT_DIR}/live_robot.py" &
  WORKER_PID=$!
  wait "$WORKER_PID"
elif [ "${1:-}" = "--live-pick-place" ]; then
  setsid python3 "${SCRIPT_DIR}/live_robot.py" --pick-place "${FAULT_ARGS[@]}" &
  WORKER_PID=$!
  wait "$WORKER_PID"
elif [ "${1:-}" = "--cell" ]; then
  timeout 120 python3 "${SCRIPT_DIR}/cell_motion.py" --cell "${2:-4}"
elif [ "${1:-}" = "--check-cells" ]; then
  timeout 120 python3 "${SCRIPT_DIR}/cell_motion.py" --check-cells
elif [ "${1:-}" = "--all-cells" ]; then
  timeout 240 python3 "${SCRIPT_DIR}/cell_motion.py" --all-cells
else
  timeout 90 python3 "${SCRIPT_DIR}/planned_motion.py"
fi
