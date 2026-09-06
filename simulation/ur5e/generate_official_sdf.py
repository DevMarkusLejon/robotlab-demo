"""Generate an inspectable official UR5e SDF from the installed ROS package."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET


def _run(command: list[str], *, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(command, input=input_text, text=True,
                                capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"required executable not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail}") from exc
    return result.stdout


def _resolve_ur_meshes(sdf_text: str, package_prefix: str) -> str:
    """Make the generated artifact runnable without a Gazebo model-path setup."""
    root = ET.fromstring(sdf_text)
    package_root = Path(package_prefix) / "share" / "ur_description"
    for uri in root.findall(".//uri"):
        value = uri.text or ""
        marker = "model://ur_description/"
        if value.startswith(marker):
            uri.text = (package_root / value[len(marker):]).resolve().as_uri()
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def generate(output: Path, world_output: Path | None = None) -> Path:
    xacro = shutil.which("xacro")
    gz = shutil.which("gz")
    if not xacro or not gz:
        raise RuntimeError("source ROS2 and install Gazebo before generating the official model")
    package_prefix = _run(["ros2", "pkg", "prefix", "ur_description"]).strip()
    xacro_path = Path(package_prefix) / "share" / "ur_description" / "urdf" / "ur.urdf.xacro"
    if not xacro_path.is_file():
        raise RuntimeError(f"ur_description xacro not found at {xacro_path}")
    urdf = _run([xacro, str(xacro_path), "ur_type:=ur5e",
                 "name:=ur5e_official", "sim_ignition:=false"])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", encoding="utf-8",
                                     delete=False) as temporary:
        temporary.write(urdf)
        temporary_path = Path(temporary.name)
    try:
        sdf_text = _run([gz, "sdf", "-p", str(temporary_path)])
    finally:
        temporary_path.unlink(missing_ok=True)
    sdf_text = _resolve_ur_meshes(sdf_text, package_prefix)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sdf_text, encoding="utf-8")
    if world_output:
        model_root = ET.fromstring(sdf_text)
        model = model_root.find("model")
        if model is None:
            raise RuntimeError("generated SDF did not contain a model")
        world_root = ET.Element("sdf", {"version": "1.9"})
        world = ET.SubElement(world_root, "world", {"name": "robotlab_official_ur5e"})
        ET.SubElement(world, "gravity").text = "0 0 -9.81"
        gui = ET.SubElement(world, "gui", {"fullscreen": "0"})
        scene = ET.SubElement(gui, "plugin", {"filename": "MinimalScene", "name": "3D View"})
        ET.SubElement(scene, "engine").text = "ogre2"
        ET.SubElement(scene, "scene").text = "scene"
        ET.SubElement(scene, "ambient_light").text = "0.65 0.65 0.65"
        ET.SubElement(scene, "background_color").text = "0.02 0.03 0.06"
        ET.SubElement(scene, "camera_pose").text = "-0.75 -0.75 0.90 0 0.68 0.78"
        clip = ET.SubElement(scene, "camera_clip")
        ET.SubElement(clip, "near").text = "0.01"
        ET.SubElement(clip, "far").text = "100"
        ET.SubElement(gui, "plugin", {"filename": "GzSceneManager", "name": "Scene Manager"})
        scene_settings = ET.SubElement(world, "scene")
        ET.SubElement(scene_settings, "ambient").text = "0.25 0.25 0.28 1"
        ET.SubElement(scene_settings, "background").text = "0.02 0.03 0.06 1"
        ET.SubElement(scene_settings, "shadows").text = "true"
        light = ET.SubElement(world, "light", {"name": "key_light", "type": "directional"})
        ET.SubElement(light, "cast_shadows").text = "true"
        ET.SubElement(light, "pose").text = "-1 -1 3 0.4 0 0"
        ET.SubElement(light, "diffuse").text = "0.95 0.95 0.9 1"
        ET.SubElement(light, "specular").text = "0.25 0.25 0.25 1"
        ET.SubElement(light, "direction").text = "0.3 0.2 -1"
        world.append(model)
        ET.indent(world_root, space="  ")
        world_output.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(world_root).write(world_output, encoding="utf-8",
                                          xml_declaration=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ur5e-official.sdf"))
    parser.add_argument("--world-output", type=Path,
                        default=Path("artifacts/ur5e-official-world.sdf"))
    args = parser.parse_args()
    try:
        path = generate(args.output, args.world_output)
    except RuntimeError as error:
        print(f"Generation failed: {error}", file=sys.stderr)
        return 2
    print(f"Generated official UR5e SDF: {path}")
    if args.world_output:
        print(f"Generated world wrapper: {args.world_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
