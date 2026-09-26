"""Automated recovery routines for common SkyTrack failure modes."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List

from skytrack_mcp.clients.docker_exec import stop_uav_python_in_container
from skytrack_mcp.diagnostics.healthcheck import run_full_system_healthcheck
from skytrack_mcp.simulation.lifecycle import boot_simulation_environment
from skytrack_mcp.ui.computer_use import send_key_name
from skytrack_mcp.ui.window import focus_skytrack_window, is_skytrack_running


async def attempt_system_recovery(issue_type: str = "auto") -> Dict[str, Any]:
    """Diagnose and recover SkyTrack environment automatically."""
    actions_taken: List[str] = []
    initial_health = await run_full_system_healthcheck()

    # 1. SkyTrack App not running
    if not initial_health["components"]["skytrack_app_running"]:
        subprocess.run(["open", "-a", "SkyTrack"], check=False)
        actions_taken.append("Launched SkyTrack.app")

    # 2. Focus window / dismiss modals
    try:
        focus_skytrack_window()
        send_key_name("escape")
        actions_taken.append("Focused window and dismissed potential modal dialogs (Escape)")
    except Exception:
        pass

    # 3. Docker containers down
    if not initial_health["components"]["docker_simulation_stack"]:
        boot_simulation_environment()
        actions_taken.append("Rebooted SkyTrack Docker simulation stack")

    # 4. Stuck python script in container
    try:
        stop_uav_python_in_container()
        actions_taken.append("Terminated any hung user-script.py inside autonomy container")
    except Exception:
        pass

    post_health = await run_full_system_healthcheck()

    return {
        "recovered": post_health["ready"],
        "actions_taken": actions_taken,
        "initial_health": initial_health,
        "post_health": post_health,
    }
