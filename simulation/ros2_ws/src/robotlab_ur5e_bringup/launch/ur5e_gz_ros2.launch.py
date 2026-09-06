"""Launch the official UR5e model with ROS2 control in Gazebo Fortress."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(get_package_share_directory("robotlab_ur5e_bringup"))
    ur_share = Path(get_package_share_directory("ur_description"))
    gz_share = Path(get_package_share_directory("ros_gz_sim"))
    world = package_share / "worlds" / "robotlab_ros2.sdf"
    controllers = package_share / "config" / "ur5e_controllers.yaml"
    xacro = ur_share / "urdf" / "ur.urdf.xacro"
    robot_description = Command([
        FindExecutable(name="xacro"), " ", str(xacro),
        " ur_type:=ur5e name:=ur5e_reference sim_ignition:=true",
        " simulation_controllers:=", str(controllers),
    ])
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(gz_share / "launch" / "gz_sim.launch.py")),
        launch_arguments={
            # Headless keeps this launch usable in CI and WSL sessions without
            # an Ogre/EGL display. Start `ign gazebo` separately for a GUI.
            "gz_args": f"-s -r {world}",
            "gz_version": "6",
        }.items(),
    )
    state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{"robot_description": robot_description}],
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=["-world", "robotlab_ros2", "-topic", "robot_description",
                    "-name", "ur5e_reference", "-x", "0.0", "-y", "0.0", "-z", "0.75"],
        output="screen",
    )
    controllers_after_spawn = TimerAction(period=4.0, actions=[
        Node(package="controller_manager", executable="spawner",
             arguments=["joint_state_broadcaster", "--controller-manager", "/controller_manager"],
             output="screen"),
        Node(package="controller_manager", executable="spawner",
             arguments=["ur5e_arm_controller", "--controller-manager", "/controller_manager"],
             output="screen"),
    ])
    return LaunchDescription([
        gazebo,
        state_publisher,
        TimerAction(period=3.0, actions=[spawn]),
        TimerAction(period=7.0, actions=[controllers_after_spawn]),
    ])
