"""Loopback-only webcam intent receiver and single UR5e simulation worker."""
import json
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from robotlab.live_intent import IntentMailbox
from robotlab.cell_execution import hover_cell
from robotlab.moveit_planner import MoveItPlanner, world_boxes
from robotlab.ros2_executor import ROS2Executor
from robotlab.telemetry import TelemetryRecorder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pick-place', action='store_true')
    args = parser.parse_args()
    import rclpy
    rclpy.init()
    node = rclpy.create_node('robotlab_live_intent')
    mailbox = IntentMailbox(mode='pick_place' if args.pick_place else 'hover')
    recorder = TelemetryRecorder(ROOT / 'artifacts/live-robot.jsonl')
    from robotlab.ros2_board_camera import ROSBoardCamera
    camera = ROSBoardCamera(node) if args.pick_place else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/camera.jpg' and camera:
                frame = camera.preview_jpeg()
                if frame is None:
                    self.reply(503, {'error': 'camera_frame_unavailable'})
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(frame)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(frame)
                return
            self.reply(200 if self.path == '/status' else 404,
                       mailbox.snapshot() if self.path == '/status' else {'error': 'not_found'})

        def do_POST(self):
            if self.path != '/intent':
                self.reply(404, {'error': 'not_found'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2048:
                    raise ValueError('invalid_body_size')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('expected_object')
                result = mailbox.submit(payload, int(time.time() * 1000))
                self.reply(200, result)
            except (ValueError, TypeError) as error:
                self.reply(400, {'error': str(error)})

    server = None
    try:
        executor = ROS2Executor(node, recorder)
        executor.current_positions(timeout=30.0)
        planner = MoveItPlanner(node)
        world = ROOT / 'simulation/ros2_ws/src/robotlab_ur5e_bringup/worlds/robotlab_ros2.sdf'
        planner.apply_boxes(world_boxes(world))
        server = ThreadingHTTPServer(('127.0.0.1', 8766), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print('UR5e webcam receiver ready at http://127.0.0.1:8766', flush=True)
        while rclpy.ok():
            cell = mailbox.take()
            if cell is None:
                rclpy.spin_once(node, timeout_sec=0.05)
                continue
            try:
                recorder.record('live_intent_accepted', cell=cell)
                if args.pick_place:
                    from pick_place import execute_pick
                    execute_pick(cell, node, recorder, on_stage=mailbox.report_stage, camera=camera)
                    recorder.record('live_pick_place_completed', cell=cell)
                else:
                    error = hover_cell(executor, planner, world, cell, recorder)
                    recorder.record('live_hover_completed', cell=cell, position_error_m=error)
                mailbox.finish()
            except Exception as error:
                recorder.record('live_execution_failed', cell=cell, reason=str(error))
                mailbox.finish(error=error)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.shutdown()
            server.server_close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
