"""Configuration and environment paths for the SkyTrack MCP Server."""

from __future__ import annotations

import os
from pathlib import Path

# Local HTTP / WebSocket endpoints exposed by SkyTrack containers
GCS_BACKEND_URL = os.environ.get("SKYTRACK_GCS_URL", "http://127.0.0.1:20002")
GCS_FEEDBACK_WS_URL = os.environ.get("SKYTRACK_GCS_WS_URL", "ws://127.0.0.1:20002/ws/feedback")
PATH_PLANNER_URL = os.environ.get("SKYTRACK_PLANNER_URL", "http://127.0.0.1:20007")
GAZEBO_URL = os.environ.get("SKYTRACK_GAZEBO_URL", "http://127.0.0.1:20005")
FILE_STORAGE_URL = os.environ.get("SKYTRACK_STORAGE_URL", "http://127.0.0.1:20080")

# Local SkyTrack Electron Application Storage
DEFAULT_CLIENT_DATA = Path.home() / "Library" / "Application Support" / "SkyTrack" / "ClientData"
CLIENT_DATA_DIR = Path(os.environ.get("SKYTRACK_CLIENT_DATA", str(DEFAULT_CLIENT_DATA)))

# Docker Container Names
GAZEBO_CONTAINER = os.environ.get("SKYTRACK_GAZEBO_CONTAINER", "skytrack-simulation-gazebo-1")
AUTONOMY_CONTAINER = os.environ.get("SKYTRACK_AUTONOMY_CONTAINER", "skytrack-simulation-skytrack-autonomy-1")
MISSION_COMPUTER_CONTAINER = os.environ.get("SKYTRACK_MC_CONTAINER", "skytrack-simulation-mission-computer-1")
MAVLINK_BRIDGE_CONTAINER = os.environ.get("SKYTRACK_MAVLINK_CONTAINER", "skytrack-deamon-mavlink-bridge-1")
GCS_BACKEND_CONTAINER = os.environ.get("SKYTRACK_GCS_CONTAINER", "skytrack-deamon-gcs-backend-1")

# Container internal paths
GAZEBO_WORLDS_DIR = "/var/www/files/px4-gz/worlds"
USER_SCRIPT_CONTAINER_PATH = (
    "/app/local_planner/lib/python3.12/site-packages/local_planner/examples/user-script.py"
)
USER_SCRIPT_LOG_CONTAINER_PATH = "/tmp/skytrack_mcp_user_script.log"
USER_SCRIPT_PID_CONTAINER_PATH = "/tmp/skytrack_mcp_user_script.pid"
