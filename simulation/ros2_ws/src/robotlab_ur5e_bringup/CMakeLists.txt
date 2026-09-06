cmake_minimum_required(VERSION 3.8)
project(robotlab_ur5e_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config worlds launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
