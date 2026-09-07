"""Save and classify an image produced by a running Gazebo camera."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    import cv2
    import rclpy
    from robotlab.ros2_board_camera import ROSBoardCamera
    rclpy.init()
    node = rclpy.create_node('board_camera_check')
    try:
        observation, frame = ROSBoardCamera(node).observe(timeout=30)
        path = ROOT / 'artifacts/board-camera.png'
        cv2.imwrite(str(path), frame)
        print(observation, flush=True)
        print(path, flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()
