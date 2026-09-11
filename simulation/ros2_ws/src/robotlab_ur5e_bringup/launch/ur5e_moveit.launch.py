"""Gazebo UR5e plus MoveIt's planning service; execution stays behind our gate."""
from pathlib import Path
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    own = Path(get_package_share_directory('robotlab_ur5e_bringup'))
    ur = Path(get_package_share_directory('ur_description'))
    moveit = Path(get_package_share_directory('ur_moveit_config'))
    description_file = LaunchConfiguration('description_file')
    description = Command([FindExecutable(name='python3'), ' ', str(own / 'urdf/render_description.py'),
        ' ', description_file,
        ' ur_type:=ur5e name:=ur sim_ignition:=true simulation_controllers:=',
        str(own / 'config/ur5e_controllers.yaml')])
    semantic = Command([FindExecutable(name='xacro'), ' ', str(moveit / 'srdf/ur.srdf.xacro'),
                        ' name:=ur'])
    ompl = yaml.safe_load((moveit / 'config/ompl_planning.yaml').read_text())
    ompl.update(planning_plugin='ompl_interface/OMPLPlanner',
        request_adapters='default_planner_request_adapters/AddTimeOptimalParameterization',
        start_state_max_bounds_error=0.01)
    return LaunchDescription([
        DeclareLaunchArgument('description_file', default_value=str(ur / 'urdf/ur.urdf.xacro')),
        DeclareLaunchArgument('world_file', default_value=str(own / 'worlds/robotlab_ros2.sdf')),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(own / 'launch/ur5e_gz_ros2.launch.py')),
                                 launch_arguments={'description_file': description_file,
                                    'world_file': LaunchConfiguration('world_file')}.items()),
        Node(package='moveit_ros_move_group', executable='move_group', output='screen',
             parameters=[
                 {'robot_description': ParameterValue(description, value_type=str),
                  'use_sim_time': True,
                  'robot_description_semantic': ParameterValue(semantic, value_type=str),
                  'robot_description_planning': yaml.safe_load((moveit / 'config/joint_limits.yaml').read_text()),
                  'move_group': ompl,
                  'allow_trajectory_execution': False,
                  'publish_robot_description_semantic': True},
                 yaml.safe_load((moveit / 'config/kinematics.yaml').read_text())['/**']['ros__parameters'],
                 yaml.safe_load((own / 'config/moveit_controllers.yaml').read_text()),
             ]),
    ])
