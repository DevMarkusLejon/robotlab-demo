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
EVIDENCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/robotlab-motion.XXXXXX")"
setsid ros2 launch robotlab_ur5e_bringup ur5e_gz_ros2.launch.py >"${LOG_FILE}" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -INT -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 2
  kill -TERM -- "-${LAUNCH_PID}" 2>/dev/null || true
  sleep 1
  kill -KILL -- "-${LAUNCH_PID}" 2>/dev/null || true
  wait "${LAUNCH_PID}" 2>/dev/null || true
}
trap cleanup EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
timeout 45 python3 "${SCRIPT_DIR}/guarded_motion.py" --telemetry "${EVIDENCE_DIR}/success.jsonl"
set +e
timeout 45 python3 "${SCRIPT_DIR}/guarded_motion.py" --drop-rate 1.0 --telemetry "${EVIDENCE_DIR}/rejected.jsonl"
REJECTION_STATUS=$?
set -e
if [ "${REJECTION_STATUS}" -ne 2 ]; then
  echo "Expected packet-loss rejection (exit 2), got ${REJECTION_STATUS}" >&2
  exit 1
fi
python3 - "${EVIDENCE_DIR}" <<'PY'
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
success = [json.loads(line) for line in (root / 'success.jsonl').read_text().splitlines()]
rejected = [json.loads(line) for line in (root / 'rejected.jsonl').read_text().splitlines()]
observations = [e for e in success if e['event'] == 'joint_target_observed']
assert len(observations) == 2 and all(e['accepted'] for e in observations)
assert any(e['event'] == 'transport_rejected' for e in rejected)
assert not any(e['event'] == 'execution_started' for e in rejected)
print('Evidence:', root)
PY
echo "ROS2 UR5e smoke test passed"
