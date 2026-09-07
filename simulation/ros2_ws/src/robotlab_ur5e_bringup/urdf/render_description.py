"""Render official UR xacro without its base-height demonstration floor.

RobotLab spawns the robot 0.75 m above the world ground. A second floor at the
robot's base plane would incorrectly collide with tokens on the worktable.
The world floor, worktable, board, and every robot collision remain in place.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET


def remove_builtin_floor(description):
    robot = ET.fromstring(description)
    for link in robot.findall('link'):
        if link.get('name') == 'ground_plane':
            for geometry in list(link):
                if geometry.tag in ('collision', 'visual'):
                    link.remove(geometry)
    return ET.tostring(robot, encoding='unicode')


if __name__ == '__main__':
    print(remove_builtin_floor(subprocess.check_output(['xacro', *sys.argv[1:]], text=True)))
