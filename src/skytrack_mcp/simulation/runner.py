"""Executes missions and flight control commands via GCS Backend, Python Autonomy container,
or deterministic kinematics trajectory simulation."""

from __future__ import annotations

import datetime
import json
import math
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from skytrack_mcp.config import (
    AUTONOMY_CONTAINER,
    CLIENT_DATA_DIR,
    GCS_BACKEND_URL,
    USER_SCRIPT_CONTAINER_PATH,
    USER_SCRIPT_LOG_CONTAINER_PATH,
    USER_SCRIPT_PID_CONTAINER_PATH,
)
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.mission.models import CanonicalMission
from skytrack_mcp.mission.parser import canonical_to_gcs_payload


async def execute_canonical_mission(
    mission: CanonicalMission,
    gcs_url: str = GCS_BACKEND_URL,
) -> Dict[str, Any]:
    """Dispatch CanonicalMission directly to GCS Backend :20002/mission/v2/execute."""
    payload = canonical_to_gcs_payload(mission)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{gcs_url}/mission/v2/execute", json=payload)
            resp.raise_for_status()
            return {
                "status_code": resp.status_code,
                "response": resp.json(),
                "submitted_payload": payload,
            }
        except httpx.HTTPStatusError as err:
            raise SkyTrackError(
                SkyTrackErrorCode.SIMULATION_START_FAILED,
                f"GCS Control API error ({err.response.status_code}): {err.response.text}",
                details={"payload": payload},
            )
        except Exception as exc:
            raise SkyTrackError(
                SkyTrackErrorCode.SIMULATOR_NOT_READY,
                f"Failed to connect to GCS Control API at {gcs_url}: {exc}",
                suggested_action="Check if skytrack-deamon-gcs-backend-1 is running",
            )


async def send_direct_flight_command(
    command: str,
    altitude_m: float = 2.5,
    smart: bool = True,
    gcs_url: str = GCS_BACKEND_URL,
) -> Dict[str, Any]:
    """Execute direct flight commands (takeoff, land, rtl, pause, resume, cancel, smart_land)."""
    cmd = command.lower().strip()
    cmd_map = {
        "takeoff": ("/flight/v2/takeoff", {"takeoff_altitude": max(1.0, float(altitude_m))}),
        "land": ("/flight/v2/land", {"smart_land": bool(smart), "timeout_sec": 60}),
        "rtl": ("/flight/v2/rtl", {"smart_rtl": bool(smart), "timeout_sec": 300}),
        "pause_mission": ("/mission/v2/pause", None),
        "resume_mission": ("/mission/v2/resume", None),
        "cancel_mission": ("/mission/v2/cancel", None),
        "smart_land": ("/mission/smartland", None),
    }
    if cmd not in cmd_map:
        raise SkyTrackError(
            SkyTrackErrorCode.MISSION_INVALID,
            f"Unsupported flight command '{command}'. Valid: {list(cmd_map.keys())}",
        )

    endpoint, body = cmd_map[cmd]
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(f"{gcs_url}{endpoint}", json=body)
            resp.raise_for_status()
            return {
                "command": cmd,
                "status_code": resp.status_code,
                "response": resp.json() if resp.content else {},
            }
        except Exception as exc:
            raise SkyTrackError(
                SkyTrackErrorCode.SIMULATION_FAILED,
                f"Flight command '{cmd}' failed: {exc}",
            )


def launch_python_script_in_container(
    python_code: str,
    wait_seconds: float = 3.0,
) -> Dict[str, Any]:
    """Deploy and launch Python UAV script inside skytrack-autonomy container."""
    # Stop prior running user-script.py
    subprocess.run(
        ["docker", "exec", AUTONOMY_CONTAINER, "pkill", "-SIGINT", "-f", "user-script.py"],
        check=False,
        capture_output=True,
    )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(python_code)
        tmp_path = tmp.name

    try:
        cp_res = subprocess.run(
            ["docker", "cp", tmp_path, f"{AUTONOMY_CONTAINER}:{USER_SCRIPT_CONTAINER_PATH}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if cp_res.returncode != 0:
            raise SkyTrackError(
                SkyTrackErrorCode.CONTAINER_NOT_FOUND,
                f"Failed to copy script to {AUTONOMY_CONTAINER}: {cp_res.stderr}",
            )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

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
    exec_res = subprocess.run(
        ["docker", "exec", AUTONOMY_CONTAINER, "bash", "-c", launch_cmd],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    pid_str = exec_res.stdout.strip().splitlines()[-1] if exec_res.stdout.strip() else ""
    if wait_seconds > 0:
        time.sleep(min(wait_seconds, 10.0))

    return {
        "status": "started",
        "container": AUTONOMY_CONTAINER,
        "pid": pid_str,
    }


def simulate_mission_to_execution_report(
    mission_id: str,
    project_id: Optional[str] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
    save_to_disk: bool = True,
) -> Dict[str, Any]:
    """Dynamically simulate flight kinematics and action events from authored mission.json & plan.json.

    Generates a synthetic execution report (`synthetic-mission-report.json`) with explicit
    provenance (`"provenance": "synthetic"`) so kinematic dry-runs are never mistaken for
    authentic SkyTrack live flight reports (`skytrack-mission-report.json`).
    """
    clean_mis = mission_id.removeprefix("mis-")
    if project_id:
        clean_prj = project_id.removeprefix("prj-")
        mis_dir = client_data_dir / f"prj-{clean_prj}" / f"mis-{clean_mis}"
    else:
        matches = list(client_data_dir.glob(f"prj-*/mis-{clean_mis}"))
        if not matches:
            raise SkyTrackError(
                SkyTrackErrorCode.MISSION_NOT_FOUND,
                f"Mission '{mission_id}' not found in {client_data_dir}",
            )
        mis_dir = matches[0]
        clean_prj = mis_dir.parent.name.removeprefix("prj-")

    mission_file = mis_dir / "mission.json"
    plan_file = mis_dir / "plan.json"

    if not mission_file.exists() or not plan_file.exists():
        raise SkyTrackError(
            SkyTrackErrorCode.MISSION_NOT_FOUND,
            f"mission.json or plan.json missing in {mis_dir}",
        )

    mission_json = json.loads(mission_file.read_text(encoding="utf-8"))
    plan_json = json.loads(plan_file.read_text(encoding="utf-8"))

    world = mission_json.get("world", "default")
    if isinstance(world, dict):
        world = world.get("name", "default")
    world = str(world or "default")

    vehicle = mission_json.get("vehicle", "x500_livox_mid_360")
    if isinstance(vehicle, dict):
        vehicle = vehicle.get("name", "x500_livox_mid_360")
    vehicle = str(vehicle or "x500_livox_mid_360")

    takeoff_altitude = float(mission_json.get("takeoffAltitude", 2.5))
    target_speed = float(mission_json.get("targetSpeed", 2.0))
    end_action = str(mission_json.get("end", {}).get("type", "rtl")).lower()

    spawn_loc = plan_json.get("spawnLocation", [0.0, 0.0, 0.0])
    spawn_x = float(spawn_loc[0]) if len(spawn_loc) >= 1 else 0.0
    spawn_y = float(spawn_loc[1]) if len(spawn_loc) >= 2 else 0.0
    spawn_z = float(spawn_loc[2]) if len(spawn_loc) >= 3 else 0.0

    sequences = plan_json.get("sequences", [])
    actions: List[Dict[str, Any]] = []
    for seq in sequences:
        actions.extend(seq.get("actions", []))

    start_dt = datetime.datetime.now(datetime.timezone.utc)

    def _ts(offset_s: float) -> str:
        dt = start_dt + datetime.timedelta(seconds=offset_s)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    t = 0.0
    events: List[Dict[str, Any]] = []

    # 1. Takeoff phase
    events.append(
        {
            "data": {
                "current_altitude": spawn_z,
                "phase": "started",
                "target_altitude": takeoff_altitude,
                "x": 0.0,
                "y": 0.0,
                "z": spawn_z,
            },
            "event": "TAKEOFF",
            "timestamp": _ts(t),
        }
    )
    events.append(
        {
            "data": {"current_mode": "LOITER", "previous_mode": None},
            "event": "FLIGHT_MODE_CHANGE",
            "timestamp": _ts(t + 0.001),
        }
    )
    events.append(
        {
            "data": {"current_mode": "TAKEOFF", "previous_mode": "LOITER"},
            "event": "FLIGHT_MODE_CHANGE",
            "timestamp": _ts(t + 0.4),
        }
    )

    climb_height = max(0.5, abs(takeoff_altitude - spawn_z))
    climb_duration = climb_height / 1.5
    for step_idx in range(1, 5):
        frac = step_idx / 4.0
        cur_z = spawn_z + (takeoff_altitude - spawn_z) * frac
        events.append(
            {
                "data": {
                    "ground_speed": 0.05,
                    "in_avoidance_mode": False,
                    "status": "Taking off before navigation",
                    "x": 0.0,
                    "y": 0.0,
                    "z": round(cur_z, 4),
                },
                "event": "NAVIGATION_STATUS",
                "timestamp": _ts(t + climb_duration * frac),
            }
        )

    t += climb_duration
    events.append(
        {
            "data": {"current_mode": "OFFBOARD", "previous_mode": "TAKEOFF"},
            "event": "FLIGHT_MODE_CHANGE",
            "timestamp": _ts(t),
        }
    )

    cur_wx, cur_wy, cur_wz = spawn_x, spawn_y, takeoff_altitude
    waypoints_defined: List[Dict[str, float]] = []
    wp_idx = 0
    total_distance = 0.0

    def _emit_action_event(action_type: str, time_s: float, wx: float, wy: float, wz: float) -> float:
        rel_x = wx - spawn_x
        rel_y = wy - spawn_y
        if action_type in ("start-recording-video", "recording_on"):
            time_s += 0.3
            events.append(
                {
                    "data": {
                        "ground_speed": 0.05,
                        "in_avoidance_mode": False,
                        "status": "Recording started",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                    },
                    "event": "NAVIGATION_STATUS",
                    "timestamp": _ts(time_s),
                }
            )
            events.append(
                {
                    "data": {
                        "status": "Recording started",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                        "world_x": wx,
                        "world_y": wy,
                    },
                    "event": "RECORDING_STARTED",
                    "timestamp": _ts(time_s),
                }
            )
        elif action_type in ("drop-ball", "drop_payload"):
            time_s += 0.5
            events.append(
                {
                    "data": {
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                        "world_x": wx,
                        "world_y": wy,
                        "world_z": wz,
                    },
                    "event": "BALL_DROP",
                    "timestamp": _ts(time_s),
                }
            )
            events.append(
                {
                    "data": {
                        "operation": "drop-ball",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                        "world_x": wx,
                        "world_y": wy,
                    },
                    "event": "PAYLOAD_TRIGGER",
                    "timestamp": _ts(time_s),
                }
            )
        elif action_type in ("stop-recording-video", "recording_off"):
            time_s += 0.5
            events.append(
                {
                    "data": {
                        "ground_speed": 0.05,
                        "in_avoidance_mode": False,
                        "status": "Recording stopped",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                    },
                    "event": "NAVIGATION_STATUS",
                    "timestamp": _ts(time_s),
                }
            )
            events.append(
                {
                    "data": {
                        "status": "Recording stopped",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                        "world_x": wx,
                        "world_y": wy,
                    },
                    "event": "RECORDING_STOPPED",
                    "timestamp": _ts(time_s),
                }
            )
        elif action_type in ("take-snapshot", "take-photo", "snapshot"):
            time_s += 0.3
            events.append(
                {
                    "data": {
                        "operation": "snapshot",
                        "x": rel_x,
                        "y": rel_y,
                        "z": wz,
                        "world_x": wx,
                        "world_y": wy,
                    },
                    "event": "CAMERA_TRIGGER",
                    "timestamp": _ts(time_s),
                }
            )
        return time_s

    # 2. Traverse actions in plan.json
    for act in actions:
        act_type = str(act.get("type", ""))
        if act_type in ("navigate", "navigation", "waypoint") or (
            "data" in act and isinstance(act["data"], list) and len(act["data"]) >= 2
        ):
            coords = act["data"]
            tx = float(coords[0])
            ty = float(coords[1])
            tz = float(coords[2]) if len(coords) >= 3 else takeoff_altitude

            dist = math.sqrt((tx - cur_wx) ** 2 + (ty - cur_wy) ** 2 + (tz - cur_wz) ** 2)
            total_distance += dist
            leg_dur = max(0.5, dist / max(0.5, target_speed))

            for step_idx in range(1, 4):
                frac = step_idx / 3.0
                sx = cur_wx + (tx - cur_wx) * frac
                sy = cur_wy + (ty - cur_wy) * frac
                sz = cur_wz + (tz - cur_wz) * frac
                events.append(
                    {
                        "data": {
                            "ground_speed": target_speed,
                            "in_avoidance_mode": False,
                            "status": f"Navigating to WP {wp_idx}",
                            "x": sx - spawn_x,
                            "y": sy - spawn_y,
                            "z": sz,
                        },
                        "event": "NAVIGATION_STATUS",
                        "timestamp": _ts(t + leg_dur * frac),
                    }
                )

            t += leg_dur
            cur_wx, cur_wy, cur_wz = tx, ty, tz
            waypoints_defined.append({"x": tx, "y": ty, "z": tz})

            events.append(
                {
                    "data": {
                        "wp_index": wp_idx,
                        "x": tx,
                        "y": ty,
                        "z": tz,
                    },
                    "event": "WAYPOINT_REACHED",
                    "timestamp": _ts(t),
                }
            )
            wp_idx += 1

            if act.get("after_action"):
                t = _emit_action_event(str(act["after_action"]), t, cur_wx, cur_wy, cur_wz)
        else:
            t = _emit_action_event(act_type, t, cur_wx, cur_wy, cur_wz)

    # 3. End action (RTL / Land)
    if end_action in ("rtl", "land"):
        ret_dist = math.sqrt((spawn_x - cur_wx) ** 2 + (spawn_y - cur_wy) ** 2)
        total_distance += ret_dist
        ret_dur = max(2.0, (ret_dist / max(0.5, target_speed)) + (cur_wz / 1.5))
        t += ret_dur
        events.append(
            {
                "data": {
                    "current_altitude": spawn_z,
                    "phase": "completed",
                    "x": 0.0,
                    "y": 0.0,
                    "z": spawn_z,
                },
                "event": "RTL" if end_action == "rtl" else "LAND",
                "timestamp": _ts(t),
            }
        )

    t += 0.5
    events.append(
        {
            "data": {
                "duration_seconds": round(t, 6),
                "execution_end_time": _ts(t),
                "execution_start_time": _ts(0.0),
            },
            "event": "MISSION_END",
            "timestamp": _ts(t),
        }
    )

    avg_speed = round(total_distance / max(1.0, t), 4)
    exec_id = str(uuid.uuid4())

    report_dict: Dict[str, Any] = {
        "execution_metadata": {
            "mission_id": clean_mis,
            "mission_name": mission_json.get("name", world),
            "world": world,
            "vehicle": vehicle,
            "status": "Succeeded",
            "duration": round(t, 6),
            "provenance": "synthetic",
            "source": "simulate_mission_to_execution_report",
        },
        "execution_report": [
            {
                "execution_id": exec_id,
                "execution_events": events,
                "status_summary": {
                    "average_ground_speed": avg_speed,
                    "duration_seconds": round(t, 6),
                    "end_time": _ts(t),
                    "failure_category_id": None,
                    "failure_reason": None,
                    "final_status": "Succeeded",
                    "max_ground_speed": round(target_speed * 1.25, 4),
                    "min_ground_speed": 0.002,
                    "start_time": _ts(0.0),
                    "total_waypoints": len(waypoints_defined),
                    "waypoints_defined": waypoints_defined,
                    "actions_defined": actions,
                    "provenance": "synthetic",
                },
            }
        ],
    }

    dest_file = mis_dir / "synthetic-mission-report.json"
    if save_to_disk:
        dest_file.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    return {
        "mission_id": clean_mis,
        "project_id": clean_prj,
        "report_path": str(dest_file),
        "provenance": "synthetic",
        "report": report_dict,
    }
