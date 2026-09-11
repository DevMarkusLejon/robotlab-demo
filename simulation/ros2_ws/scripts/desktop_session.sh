#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
STOP_FILE="$1"
MODE="${2:---game}"
FAULT="${3:-}"
case "$MODE" in --game|--live-pick-place) ;; *) exit 2 ;; esac
cd "$ROOT"
bash simulation/ros2_ws/scripts/moveit_smoke_test.sh "$MODE" "$FAULT" &
SESSION_PID=$!
cleanup() {
  kill -TERM "$SESSION_PID" 2>/dev/null || true
  wait "$SESSION_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM
while kill -0 "$SESSION_PID" 2>/dev/null; do
  if [ -f "$STOP_FILE" ]; then exit 0; fi
  sleep 0.5
done
wait "$SESSION_PID"
