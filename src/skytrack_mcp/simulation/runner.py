"""Executes missions and flight control commands via GCS Backend or Python Autonomy container."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from skytrack_mcp.config import (
    AUTONOMY_CONTAINER,
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
