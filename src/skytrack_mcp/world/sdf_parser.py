"""Parses Gazebo .sdf XML files to extract 3D obstacles, models, and world metadata."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from skytrack_mcp.config import GAZEBO_CONTAINER, GAZEBO_WORLDS_DIR
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.world.geometry import (
    compose_pose_2d,
    compute_rotated_aabb,
    parse_pose,
)

LOCAL_WORLD_CACHE_DIR = Path(__file__).resolve().parent.parent / "worlds"


def read_sdf_content(world_name: str) -> str:
    """Read .sdf XML content from local cache or Gazebo Docker container."""
    clean_name = world_name.removesuffix(".sdf")
    cached_sdf = LOCAL_WORLD_CACHE_DIR / f"{clean_name}.sdf"
    if cached_sdf.exists():
        return cached_sdf.read_text(encoding="utf-8")

    sdf_path = f"{GAZEBO_WORLDS_DIR}/{clean_name}.sdf"
    res = subprocess.run(
        ["docker", "exec", GAZEBO_CONTAINER, "cat", sdf_path],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise SkyTrackError(
            SkyTrackErrorCode.WORLD_NOT_FOUND,
            f"Could not load SDF world '{world_name}' from container or cache: {res.stderr}",
            suggested_action="Verify world name with list_gazebo_worlds()",
        )
    return res.stdout


def parse_world_sdf(world_name: str) -> Dict[str, Any]:
    """Parse a Gazebo world .sdf into structured obstacles, included models, and coordinates."""
    clean_name = world_name.removesuffix(".sdf")
    sdf_xml = read_sdf_content(clean_name)

    try:
        root = ET.fromstring(sdf_xml)
    except Exception as exc:
        raise SkyTrackError(
            SkyTrackErrorCode.INTERNAL_ERROR,
            f"Failed to parse SDF XML for world '{world_name}': {exc}",
        )

    world_el = root.find("world")
    if world_el is None:
        world_el = root

    sph_el = world_el.find("spherical_coordinates")
    spherical_coords: Dict[str, Any] = {}
    if sph_el is not None:
        for child in sph_el:
            try:
                spherical_coords[child.tag] = float(child.text or "0")
            except ValueError:
                spherical_coords[child.tag] = (child.text or "").strip()

    obstacles: List[Dict[str, Any]] = []
    included_models: List[Dict[str, Any]] = []

    for inc_el in world_el.findall("include"):
        uri = (inc_el.findtext("uri") or "").strip()
        name = (inc_el.findtext("name") or uri.split("/")[-1] or "included").strip()
        pose = parse_pose(inc_el.findtext("pose"))
        included_models.append(
            {
                "name": name,
                "uri": uri,
                "pose": {
                    "x": round(pose[0], 3),
                    "y": round(pose[1], 3),
                    "z": round(pose[2], 3),
                    "yaw": round(pose[5], 3),
                },
            }
        )

    for model_el in world_el.findall("model"):
        model_name = model_el.attrib.get("name", "unnamed_model")
        if model_name in ("ground_plane",):
            continue
        model_pose = parse_pose(model_el.findtext("pose"))

        links = model_el.findall("link")
        if not links:
            obstacles.append(
                {
                    "model": model_name,
                    "collision": "origin",
                    "type": "model_origin",
                    "center": [round(model_pose[0], 3), round(model_pose[1], 3), round(model_pose[2], 3)],
                    "size": [1.0, 1.0, 2.0],
                    "aabb": compute_rotated_aabb(
                        model_pose[0], model_pose[1], model_pose[2] + 1.0, 1.0, 1.0, 2.0, model_pose[5]
                    ),
                }
            )
            continue

        for link_el in links:
            link_pose = compose_pose_2d(model_pose, parse_pose(link_el.findtext("pose")))
            for col_el in link_el.findall("collision"):
                col_name = col_el.attrib.get("name", "collision")
                if col_name.lower() in ("floor", "ground", "ground_plane"):
                    continue
                col_pose = compose_pose_2d(link_pose, parse_pose(col_el.findtext("pose")))
                geom_el = col_el.find("geometry")
                if geom_el is None:
                    continue

                box_el = geom_el.find("box")
                cyl_el = geom_el.find("cylinder")
                sph_g_el = geom_el.find("sphere")

                if box_el is not None:
                    size_str = box_el.findtext("size") or "1 1 1"
                    sx, sy, sz = [float(v) for v in size_str.split()[:3]]
                    if sz < 0.35 and col_pose[2] <= 0.25:
                        continue
                    aabb = compute_rotated_aabb(
                        col_pose[0], col_pose[1], col_pose[2], sx, sy, sz, col_pose[5]
                    )
                    obstacles.append(
                        {
                            "model": model_name,
                            "collision": col_name,
                            "type": "box",
                            "center": [round(col_pose[0], 3), round(col_pose[1], 3), round(col_pose[2], 3)],
                            "size": [round(sx, 3), round(sy, 3), round(sz, 3)],
                            "aabb": aabb,
                        }
                    )
                elif cyl_el is not None:
                    r = float(cyl_el.findtext("radius") or "0.5")
                    length = float(cyl_el.findtext("length") or "1.0")
                    aabb = compute_rotated_aabb(
                        col_pose[0], col_pose[1], col_pose[2], 2 * r, 2 * r, length, 0.0
                    )
                    obstacles.append(
                        {
                            "model": model_name,
                            "collision": col_name,
                            "type": "cylinder",
                            "center": [round(col_pose[0], 3), round(col_pose[1], 3), round(col_pose[2], 3)],
                            "size": [round(2 * r, 3), round(2 * r, 3), round(length, 3)],
                            "aabb": aabb,
                        }
                    )
                elif sph_g_el is not None:
                    r = float(sph_g_el.findtext("radius") or "0.5")
                    aabb = compute_rotated_aabb(
                        col_pose[0], col_pose[1], col_pose[2], 2 * r, 2 * r, 2 * r, 0.0
                    )
                    obstacles.append(
                        {
                            "model": model_name,
                            "collision": col_name,
                            "type": "sphere",
                            "center": [round(col_pose[0], 3), round(col_pose[1], 3), round(col_pose[2], 3)],
                            "size": [round(2 * r, 3), round(2 * r, 3), round(2 * r, 3)],
                            "aabb": aabb,
                        }
                    )

    return {
        "world": clean_name,
        "spherical_coordinates": spherical_coords,
        "total_collision_boxes": len(obstacles),
        "obstacles": obstacles,
        "included_models": included_models,
    }
