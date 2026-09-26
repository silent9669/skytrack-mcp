"""Comprehensive system diagnostics and health check across all SkyTrack integration surfaces."""

from __future__ import annotations

import httpx
from pathlib import Path
from typing import Any, Dict

from skytrack_mcp.clients.cloud_client import get_cloud_auth_credentials
from skytrack_mcp.clients.docker_exec import fetch_live_mavlink_telemetry, get_simulation_health
from skytrack_mcp.config import CLIENT_DATA_DIR, GCS_BACKEND_URL, PATH_PLANNER_URL
from skytrack_mcp.ui.window import is_skytrack_running


async def run_full_system_healthcheck() -> Dict[str, Any]:
    """Execute end-to-end diagnostic checks across all SkyTrack layers."""
    app_running = is_skytrack_running()
    storage_accessible = CLIENT_DATA_DIR.exists()

    creds = get_cloud_auth_credentials()
    auth_ok = bool(creds.get("access_token") and creds.get("csrf_token"))

    # Docker containers
    try:
        docker_health = get_simulation_health()
    except Exception as exc:
        docker_health = {"all_healthy": False, "error": str(exc)}

    # GCS Backend (:20002)
    gcs_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{GCS_BACKEND_URL}/docs")
            gcs_ok = resp.status_code == 200
    except Exception:
        gcs_ok = False

    # Path Planner (:20007)
    planner_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{PATH_PLANNER_URL}/health")
            planner_ok = resp.status_code == 200
    except Exception:
        planner_ok = False

    # Telemetry stream
    try:
        telem = fetch_live_mavlink_telemetry()
        telem_connected = bool(telem.get("connected"))
    except Exception:
        telem_connected = False

    overall_ready = (
        app_running
        and storage_accessible
        and auth_ok
        and docker_health.get("all_healthy", False)
        and gcs_ok
        and planner_ok
    )

    return {
        "ready": overall_ready,
        "components": {
            "skytrack_app_running": app_running,
            "client_data_storage": storage_accessible,
            "cloud_auth_tokens": auth_ok,
            "docker_simulation_stack": docker_health.get("all_healthy", False),
            "gcs_backend_api_20002": gcs_ok,
            "path_planner_api_20007": planner_ok,
            "mavlink_telemetry_stream": telem_connected,
        },
        "docker_details": docker_health,
    }
