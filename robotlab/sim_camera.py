"""Overhead Gazebo camera geometry; images still come from the renderer."""
import math
import xml.etree.ElementTree as ET

from .calibration import BoardCalibration

IMAGE_SIZE = 640
HFOV = 1.0
CAMERA_Z = 1.6
BOARD_Z = 0.7375
TOPIC = '/robotlab/board_camera/image'


def add_camera(world):
    # Explicit systems are needed once a world supplies any system plugin.
    for library, name in [('physics', 'Physics'), ('user-commands', 'UserCommands'),
                          ('scene-broadcaster', 'SceneBroadcaster'), ('sensors', 'Sensors')]:
        plugin = ET.SubElement(world, 'plugin', filename=f'ignition-gazebo-{library}-system',
                               name=f'ignition::gazebo::systems::{name}')
        if name == 'Sensors':
            ET.SubElement(plugin, 'render_engine').text = 'ogre'
    world.append(ET.fromstring(f'''<model name="board_camera"><static>true</static>
      <pose>0.45 0 {CAMERA_Z} 0 {math.pi / 2} {math.pi / 2}</pose><link name="camera">
      <sensor name="overhead" type="camera"><always_on>true</always_on><update_rate>10</update_rate>
        <topic>{TOPIC}</topic><camera><horizontal_fov>{HFOV}</horizontal_fov>
          <image><width>{IMAGE_SIZE}</width><height>{IMAGE_SIZE}</height><format>R8G8B8</format></image>
          <clip><near>0.02</near><far>5</far></clip>
        </camera></sensor></link></model>'''))


def board_calibration():
    # Pinhole projection of known board corners. Physical cameras need measured calibration.
    center = IMAGE_SIZE / 2
    focal = center / math.tan(HFOV / 2)
    half = focal * 0.225 / (CAMERA_Z - BOARD_Z)
    return BoardCalibration(((center-half, center-half), (center+half, center-half),
                             (center+half, center+half), (center-half, center+half)))
