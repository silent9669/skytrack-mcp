"""Docker & Gazebo SDF inspection, live MAVLink telemetry, and ROS 2 Python script execution."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skytrack_mcp.config import (
    AUTONOMY_CONTAINER,
    CLIENT_DATA_DIR,
    GAZEBO_CONTAINER,
    GAZEBO_WORLDS_DIR,
    MAVLINK_BRIDGE_CONTAINER,
    USER_SCRIPT_CONTAINER_PATH,
    USER_SCRIPT_LOG_CONTAINER_PATH,
    USER_SCRIPT_PID_CONTAINER_PATH,
)

LOCAL_WORLD_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".world_cache"


def _run_cmd(args: List[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def list_gazebo_worlds() -> List[str]:
    """List all .sdf world names available in local world cache or Gazebo container."""
    if LOCAL_WORLD_CACHE_DIR.exists():
        cached = sorted(p.stem for p in LOCAL_WORLD_CACHE_DIR.glob("*.sdf"))
        if cached:
            return cached
    res = _run_cmd(
        ["docker", "exec", GAZEBO_CONTAINER, "ls", GAZEBO_WORLDS_DIR],
        timeout=10.0,
    )
    if res.returncode != 0:
        return []
    worlds = [
        line.strip().removesuffix(".sdf")
        for line in res.stdout.splitlines()
        if line.strip().endswith(".sdf")
    ]
    return sorted(worlds)


def _parse_pose(pose_str: Optional[str]) -> Tuple[float, float, float, float, float, float]:
    if not pose_str:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    parts = [float(p) for p in pose_str.strip().split()[:6]]
    while len(parts) < 6:
        parts.append(0.0)
    return (parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])


def _compose_pose_2d(
    parent: Tuple[float, float, float, float, float, float],
    child: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float, float, float, float, float]:
    px, py, pz, pr, pp, pyaw = parent
    cx, cy, cz, cr, cp, cyaw = child
    cos_y = math.cos(pyaw)
    sin_y = math.sin(pyaw)
    wx = px + cx * cos_y - cy * sin_y
    wy = py + cx * sin_y + cy * cos_y
    wz = pz + cz
    return (wx, wy, wz, pr + cr, pp + cp, pyaw + cyaw)


def _compute_rotated_aabb(
    cx: float,
    cy: float,
    cz: float,
    sx: float,
    sy: float,
    sz: float,
    yaw: float,
) -> Dict[str, float]:
    cos_y = abs(math.cos(yaw))
    sin_y = abs(math.sin(yaw))
    ext_x = (sx * cos_y + sy * sin_y) / 2.0
    ext_y = (sx * sin_y + sy * cos_y) / 2.0
    ext_z = sz / 2.0
    return {
        "min_x": round(cx - ext_x, 3),
        "max_x": round(cx + ext_x, 3),
        "min_y": round(cy - ext_y, 3),
        "max_y": round(cy + ext_y, 3),
        "min_z": round(cz - ext_z, 3),
        "max_z": round(cz + ext_z, 3),
    }


def inspect_world_sdf(
    world_name: str,
    slice_altitude_m: float = 2.5,
    grid_half_size_m: float = 15.0,
    grid_resolution: int = 31,
) -> Dict[str, Any]:
    """Parse a Gazebo .sdf world file and return obstacles, included models, spherical coords,
    and a 2D ASCII top-down occupancy map at slice_altitude_m."""
    clean_name = world_name.removesuffix(".sdf")
    cached_sdf = LOCAL_WORLD_CACHE_DIR / f"{clean_name}.sdf"
    if cached_sdf.exists():
        sdf_xml_text = cached_sdf.read_text(encoding="utf-8")
    else:
        sdf_path = f"{GAZEBO_WORLDS_DIR}/{clean_name}.sdf"
        res = _run_cmd(["docker", "exec", GAZEBO_CONTAINER, "cat", sdf_path], timeout=10.0)
        if res.returncode != 0 or not res.stdout.strip():
            raise ValueError(f"Could not read SDF world '{world_name}' at {sdf_path}: {res.stderr}")
        sdf_xml_text = res.stdout

    root = ET.fromstring(sdf_xml_text)
    world_el = root.find("world")
    if world_el is None:
        world_el = root

    # Spherical coordinates
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
        pose = _parse_pose(inc_el.findtext("pose"))
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
        if model_name == "ground_plane":
            continue
        model_pose = _parse_pose(model_el.findtext("pose"))

        links = model_el.findall("link")
        if not links:
            obstacles.append(
                {
                    "model": model_name,
                    "collision": "origin",
                    "type": "model_origin",
                    "center": [round(model_pose[0], 3), round(model_pose[1], 3), round(model_pose[2], 3)],
                    "size": [1.0, 1.0, 2.0],
                    "aabb": _compute_rotated_aabb(
                        model_pose[0], model_pose[1], model_pose[2] + 1.0, 1.0, 1.0, 2.0, model_pose[5]
                    ),
                }
            )
            continue

        for link_el in links:
            link_pose = _compose_pose_2d(model_pose, _parse_pose(link_el.findtext("pose")))
            for col_el in link_el.findall("collision"):
                col_name = col_el.attrib.get("name", "collision")
                if col_name.lower() in ("floor", "ground", "ground_plane"):
                    continue
                col_pose = _compose_pose_2d(link_pose, _parse_pose(col_el.findtext("pose")))
                geom_el = col_el.find("geometry")
                if geom_el is None:
                    continue

                box_el = geom_el.find("box")
                cyl_el = geom_el.find("cylinder")
                sph_g_el = geom_el.find("sphere")

                if box_el is not None:
                    size_str = box_el.findtext("size") or "1 1 1"
                    sx, sy, sz = [float(v) for v in size_str.split()[:3]]
                    # Ignore flat floors (very thin z near z <= 0.2)
                    if sz < 0.35 and col_pose[2] <= 0.25:
                        continue
                    aabb = _compute_rotated_aabb(
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
                    aabb = _compute_rotated_aabb(
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
                    aabb = _compute_rotated_aabb(
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

    # Filter obstacles active at slice_altitude_m
    slice_obstacles = [
        obs
        for obs in obstacles
        if obs["aabb"]["min_z"] <= slice_altitude_m <= obs["aabb"]["max_z"]
    ]

    # Build 2D ASCII Top-Down Grid (X=East horizontal, Y=North vertical)
    n = max(11, min(61, grid_resolution))
    step = (2.0 * grid_half_size_m) / (n - 1)
    grid_lines: List[str] = []
    header = (
        f"Top-Down Map Slice at z={slice_altitude_m}m | "
        f"X (East): [{-grid_half_size_m:.1f}m .. +{grid_half_size_m:.1f}m], "
        f"Y (North): [+{grid_half_size_m:.1f}m .. {-grid_half_size_m:.1f}m] | "
        f"'#'=Obstacle, 'S'=Origin(0,0), '.'=Free"
    )
    grid_lines.append(header)

    for row in range(n):
        # Top row = +Y (North), bottom row = -Y (South)
        y_val = grid_half_size_m - row * step
        row_chars: List[str] = []
        for col in range(n):
            x_val = -grid_half_size_m + col * step
            if abs(x_val) < step * 0.55 and abs(y_val) < step * 0.55:
                row_chars.append("S")
                continue
            hit = False
            for obs in slice_obstacles:
                b = obs["aabb"]
                if b["min_x"] <= x_val <= b["max_x"] and b["min_y"] <= y_val <= b["max_y"]:
                    hit = True
                    break
            row_chars.append("#" if hit else ".")
        grid_lines.append(f"Y={y_val:+6.1f}m | {''.join(row_chars)}")

    return {
        "world": clean_name,
        "spherical_coordinates": spherical_coords,
        "total_collision_boxes": len(obstacles),
        "obstacles_at_slice_altitude": len(slice_obstacles),
        "slice_altitude_m": slice_altitude_m,
        "obstacles": obstacles,
        "included_models": included_models,
        "ascii_map_2d": "\n".join(grid_lines),
    }


def _segment_intersects_aabb(
    p0: Tuple[float, float, float],
    p1: Tuple[float, float, float],
    aabb: Dict[str, float],
    clearance: float = 0.35,
) -> bool:
    """Slab method 3D segment vs inflated AABB intersection test."""
    bounds = [
        (aabb["min_x"] - clearance, aabb["max_x"] + clearance),
        (aabb["min_y"] - clearance, aabb["max_y"] + clearance),
        (aabb["min_z"] - clearance, aabb["max_z"] + clearance),
    ]
    t_min = 0.0
    t_max = 1.0
    for i in range(3):
        d = p1[i] - p0[i]
        b_min, b_max = bounds[i]
        if abs(d) < 1e-9:
            if p0[i] < b_min or p0[i] > b_max:
                return False
        else:
            inv_d = 1.0 / d
            t1 = (b_min - p0[i]) * inv_d
            t2 = (b_max - p0[i]) * inv_d
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return False
    return True


def check_waypoints_collisions(
    world_name: str,
    waypoints: List[List[float]],
    clearance_m: float = 0.4,
) -> Dict[str, Any]:
    """Check a list of [x, y, z] ENU waypoints against all 3D obstacles in world_name."""
    world_info = inspect_world_sdf(world_name)
    obstacles = world_info["obstacles"]
    conflicts: List[Dict[str, Any]] = []

    for idx in range(len(waypoints) - 1):
        p0 = (float(waypoints[idx][0]), float(waypoints[idx][1]), float(waypoints[idx][2]))
        p1 = (
            float(waypoints[idx + 1][0]),
            float(waypoints[idx + 1][1]),
            float(waypoints[idx + 1][2]),
        )
        for obs in obstacles:
            if _segment_intersects_aabb(p0, p1, obs["aabb"], clearance=clearance_m):
                conflicts.append(
                    {
                        "leg_index": idx,
                        "from": list(p0),
                        "to": list(p1),
                        "obstacle_model": obs["model"],
                        "obstacle_collision": obs["collision"],
                        "obstacle_aabb": obs["aabb"],
                    }
                )

    return {
        "world": world_name,
        "is_collision_free": len(conflicts) == 0,
        "clearance_m": clearance_m,
        "legs_checked": max(0, len(waypoints) - 1),
        "conflicts": conflicts,
    }


def fetch_live_mavlink_telemetry() -> Dict[str, Any]:
    """Read real-time telemetry state from the mavlink-bridge WebSocket and compute local ENU/NED."""
    py_snippet = (
        "import asyncio, websockets\n"
        "async def get():\n"
        "    async with websockets.connect('ws://127.0.0.1:9005') as ws:\n"
        "        print(await ws.recv())\n"
        "asyncio.run(get())\n"
    )
    res = _run_cmd(
        ["docker", "exec", MAVLINK_BRIDGE_CONTAINER, "python3", "-c", py_snippet],
        timeout=5.0,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return {"connected": False, "error": res.stderr.strip() or "No telemetry response"}

    raw = json.loads(res.stdout.strip().splitlines()[-1])

    # Compute local ENU and NED meters relative to home_point if GPS & home_point are present
    pos = raw.get("position") or {}
    home = raw.get("home_point") or {}
    local_enu: Optional[Dict[str, float]] = None
    local_ned: Optional[Dict[str, float]] = None

    if pos.get("lat") is not None and home.get("lat") is not None:
        lat_rad = math.radians(float(home["lat"]))
        d_lat = float(pos["lat"]) - float(home["lat"])
        d_lng = float(pos["lng"]) - float(home["lng"])
        north_m = d_lat * 111132.92
        east_m = d_lng * 111412.84 * math.cos(lat_rad)
        up_m = float(pos.get("altitude", 0.0))
        local_enu = {
            "x_east_m": round(east_m, 3),
            "y_north_m": round(north_m, 3),
            "z_up_m": round(up_m, 3),
        }
        local_ned = {
            "north_m": round(north_m, 3),
            "east_m": round(east_m, 3),
            "down_m": round(-up_m, 3),
        }

    return {
        "connected": bool(raw.get("connection_state", True)),
        "is_armed": raw.get("is_armed", False),
        "landed_state": raw.get("landed_state", "UNKNOWN"),
        "flight_mode": raw.get("flight_mode", "UNKNOWN"),
        "battery_percentage": raw.get("battery_percentage"),
        "heading_deg": raw.get("heading"),
        "attitude_deg": {
            "roll": round(float(raw.get("roll_deg") or 0.0), 2),
            "pitch": round(float(raw.get("pitch_deg") or 0.0), 2),
            "yaw": round(float(raw.get("yaw_deg") or 0.0), 2),
        },
        "local_enu_m": local_enu,
        "local_ned_m": local_ned,
        "gps_position": pos,
        "home_point": home,
        "ned_velocity": raw.get("ned_velocity"),
        "gps_status": raw.get("gps"),
    }


def get_simulation_health() -> Dict[str, Any]:
    """Check health and running status of all SkyTrack Docker containers."""
    res = _run_cmd(
        ["docker", "ps", "-a", "--filter", "name=skytrack", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
        timeout=10.0,
    )
    containers = {}
    if res.returncode == 0 and res.stdout.strip():
        for line in res.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[0]
                status = parts[1]
                ports = parts[2] if len(parts) > 2 else ""
                containers[name] = {
                    "running": "Up" in status,
                    "status": status,
                    "ports": ports,
                }
    all_core = [
        "skytrack-deamon-gcs-backend-1",
        "skytrack-deamon-mavlink-bridge-1",
        "skytrack-simulation-gazebo-1",
        "skytrack-simulation-px4-1",
        "skytrack-simulation-mission-computer-1",
        "skytrack-simulation-skytrack-autonomy-1",
    ]
    return {
        "all_healthy": all(containers.get(c, {}).get("running", False) for c in all_core),
        "containers": containers,
    }


def start_simulation_stack(
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    spawn_pose: Optional[List[float]] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Configure and start the SkyTrack deamon and simulation Docker stacks."""
    deamon_compose = client_data_dir / "docker" / "deamon" / "docker-compose.yml"
    sim_compose = client_data_dir / "docker" / "local-sim" / "docker-compose.yml"

    if not deamon_compose.exists() or not sim_compose.exists():
        raise FileNotFoundError("SkyTrack docker compose files not found in ClientData.")

    pose_str = (
        f"{spawn_pose[0]:.3f},{spawn_pose[1]:.3f},{spawn_pose[2]:.3f},0.000,0.000,0.000"
        if spawn_pose and len(spawn_pose) >= 3
        else "0.000,0.000,0.024,0.000,0.000,0.000"
    )

    # 1. Update local-sim compose with target world & vehicle
    sim_text = sim_compose.read_text(encoding="utf-8")
    sim_text = re.sub(r"GZ_WORLD:\s*.*", f"GZ_WORLD: {world}", sim_text)
    sim_text = re.sub(r"PX4_GZ_WORLD:\s*.*", f"PX4_GZ_WORLD: {world}", sim_text)
    sim_text = re.sub(r"PX4_SIM_MODEL:\s*.*", f"PX4_SIM_MODEL: {vehicle}", sim_text)
    sim_text = re.sub(r"PX4_GZ_MODEL_POSE:\s*.*", f"PX4_GZ_MODEL_POSE: {pose_str}", sim_text)
    sim_compose.write_text(sim_text, encoding="utf-8")

    # 2. Run docker compose up -d
    env_vars = {
        "APP_STORAGE_PATH": str(client_data_dir),
    }
    import os
    merged_env = {**os.environ, **env_vars}

    res_deamon = subprocess.run(
        ["docker", "compose", "-f", str(deamon_compose), "up", "-d"],
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )

    res_sim = subprocess.run(
        ["docker", "compose", "-f", str(sim_compose), "up", "-d", "--force-recreate"],
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )

    health = get_simulation_health()
    return {
        "world": world,
        "vehicle": vehicle,
        "spawn_pose": pose_str,
        "deamon_status": "ok" if res_deamon.returncode == 0 else res_deamon.stderr,
        "simulation_status": "ok" if res_sim.returncode == 0 else res_sim.stderr,
        "health": health,
    }


def stop_simulation_stack(client_data_dir: Path = CLIENT_DATA_DIR) -> Dict[str, Any]:
    """Stop the SkyTrack simulation Docker stack."""
    sim_compose = client_data_dir / "docker" / "local-sim" / "docker-compose.yml"
    import os
    merged_env = {**os.environ, "APP_STORAGE_PATH": str(client_data_dir)}
    res = subprocess.run(
        ["docker", "compose", "-f", str(sim_compose), "stop"],
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "stopped": res.returncode == 0,
        "message": res.stdout or res.stderr,
    }



def stop_uav_python_in_container() -> Dict[str, Any]:
    """Terminate any running user-script.py inside skytrack-simulation-skytrack-autonomy-1."""
    kill_cmd = (
        "pkill -SIGINT -f 'user-script.py' || true; "
        "sleep 0.3; "
        "pkill -SIGTERM -f 'user-script.py' || true"
    )
    res = _run_cmd(["docker", "exec", AUTONOMY_CONTAINER, "bash", "-c", kill_cmd], timeout=8.0)
    return {
        "stopped": True,
        "container": AUTONOMY_CONTAINER,
        "returncode": res.returncode,
    }


def run_uav_python_in_container(
    python_code: str,
    background: bool = True,
    wait_seconds: float = 3.5,
) -> Dict[str, Any]:
    """Copy python_code into the autonomy container and run it with ROS 2 Jazzy & local_planner."""
    # 1. Stop any prior running user-script.py
    stop_uav_python_in_container()

    # 2. Write to temporary file and docker cp into container
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(python_code)
        tmp_path = tmp.name

    try:
        cp_res = _run_cmd(
            ["docker", "cp", tmp_path, f"{AUTONOMY_CONTAINER}:{USER_SCRIPT_CONTAINER_PATH}"],
            timeout=10.0,
        )
        if cp_res.returncode != 0:
            raise RuntimeError(f"Failed to copy script to {AUTONOMY_CONTAINER}: {cp_res.stderr}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # 3. Launch inside ROS 2 Jazzy environment
    if background:
        launch_cmd = (
            f"rm -f {USER_SCRIPT_LOG_CONTAINER_PATH} {USER_SCRIPT_PID_CONTAINER_PATH} && "
            f"source /opt/ros/jazzy/setup.bash && "
            f"source /app/setup.sh && "
            f"export RCUTILS_LOGGING_USE_STDOUT=1 && "
            f"export PYTHONUNBUFFERED=1 && "
            f"nohup python3 -u {USER_SCRIPT_CONTAINER_PATH} "
            f"> {USER_SCRIPT_LOG_CONTAINER_PATH} 2>&1 < /dev/null & "
            f"echo $! > {USER_SCRIPT_PID_CONTAINER_PATH} && "
            f"cat {USER_SCRIPT_PID_CONTAINER_PATH}"
        )
        exec_res = _run_cmd(
            ["docker", "exec", AUTONOMY_CONTAINER, "bash", "-c", launch_cmd],
            timeout=10.0,
        )
        pid_str = exec_res.stdout.strip().splitlines()[-1] if exec_res.stdout.strip() else ""
        if wait_seconds > 0:
            time.sleep(min(wait_seconds, 10.0))
        logs_info = read_uav_python_logs(tail_lines=60)
        return {
            "status": "started_in_background",
            "container": AUTONOMY_CONTAINER,
            "pid": pid_str,
            "is_still_running": logs_info["is_running"],
            "initial_logs": logs_info["logs"],
        }
    else:
        fg_cmd = (
            f"source /opt/ros/jazzy/setup.bash && "
            f"source /app/setup.sh && "
            f"export RCUTILS_LOGGING_USE_STDOUT=1 && "
            f"export PYTHONUNBUFFERED=1 && "
            f"python3 -u {USER_SCRIPT_CONTAINER_PATH}"
        )
        exec_res = _run_cmd(
            ["docker", "exec", AUTONOMY_CONTAINER, "bash", "-c", fg_cmd],
            timeout=max(5.0, wait_seconds),
        )
        return {
            "status": "completed" if exec_res.returncode == 0 else "error",
            "returncode": exec_res.returncode,
            "stdout": exec_res.stdout,
            "stderr": exec_res.stderr,
        }


def read_uav_python_logs(tail_lines: int = 80) -> Dict[str, Any]:
    """Read the execution logs and running status of user-script.py in skytrack-autonomy."""
    check_cmd = (
        f"if pgrep -f '{USER_SCRIPT_CONTAINER_PATH}' >/dev/null 2>&1; then echo 'RUNNING'; else echo 'STOPPED'; fi; "
        f"echo '---LOG_SEP---'; "
        f"tail -n {int(tail_lines)} {USER_SCRIPT_LOG_CONTAINER_PATH} 2>/dev/null || true"
    )
    res = _run_cmd(["docker", "exec", AUTONOMY_CONTAINER, "bash", "-c", check_cmd], timeout=8.0)
    parts = res.stdout.split("---LOG_SEP---\n", 1)
    state_str = parts[0].strip() if parts else "UNKNOWN"
    logs_str = parts[1] if len(parts) > 1 else ""
    return {
        "is_running": state_str == "RUNNING",
        "state": state_str,
        "logs": logs_str.strip(),
    }
