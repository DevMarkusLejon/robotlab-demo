"""Exercise intent gates and measured ROS2 execution in simulation.

This small joint-space motion verifies the execution adapter, not a board-cell
pose or a pick/place. No webcam or collision planner is involved in this test.
"""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from robotlab.intent import HandIntent, IntentGate
from robotlab.network import NetworkSimulator
from robotlab.pipeline import SharedAutonomyPipeline
from robotlab.ros2_executor import ROS2Executor
from robotlab.safety import JointPoint
from robotlab.telemetry import TelemetryRecorder


def main():
    import rclpy
    from rclpy.parameter import Parameter
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drop-rate', type=float, default=0.0)
    parser.add_argument('--telemetry', default='artifacts/ros2-guarded-motion.jsonl')
    args = parser.parse_args()
    if not 0 <= args.drop_rate <= 1:
        parser.error('drop-rate must be in [0, 1]')
    rclpy.init()
    node = rclpy.create_node('robotlab_guarded_motion',
                            parameter_overrides=[Parameter('use_sim_time', value=True)])
    recorder = TelemetryRecorder(args.telemetry)
    try:
        executor = ROS2Executor(node, recorder)
        start = executor.current_positions(timeout=30.0)
        target = (start[0] + 0.1, *start[1:])
        points = (JointPoint(2.0, target), JointPoint(4.0, start))
        pipeline = SharedAutonomyPipeline(gate=IntentGate(stable_frames=3),
            network=NetworkSimulator(drop_rate=args.drop_rate, seed=0), telemetry=recorder)
        for _ in range(3):
            now = int(time.monotonic() * 1000)
            result = pipeline.handle_intent(HandIntent(0.5, 0.5, 0.99, now, track_id=1),
                now_ms=now, legal_cells={4}, trajectory=points, deadline_ms=now + 500)
        if result.status != 'ready':
            recorder.record('demo_aborted', reason=result.reason)
            print('Intent blocked:', result.reason)
            return 2
        executor.execute((JointPoint(2.0, target),))
        executor.execute((JointPoint(2.0, start),))
        recorder.record('motion_test_completed', verification='controller_and_joint_states')
        print('Guarded ROS2 motion verified against joint states')
        return 0
    except RuntimeError as error:
        recorder.record('demo_aborted', reason=str(error))
        print(str(error), file=sys.stderr)
        return 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
