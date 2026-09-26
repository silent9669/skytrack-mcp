"""Standardized MCP tool handlers grouped across all SkyTrack capability layers."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from skytrack_mcp.clients.cloud_client import (
    create_cloud_mission,
    list_cloud_projects,
    update_cloud_mission,
)
from skytrack_mcp.clients.docker_exec import (
    check_waypoints_collisions,
    fetch_live_mavlink_telemetry,
    get_simulation_health,
    inspect_world_sdf,
    list_gazebo_worlds,
    read_uav_python_logs,
    run_uav_python_in_container,
    start_simulation_stack,
    stop_simulation_stack,
    stop_uav_python_in_container,
)
from skytrack_mcp.clients.gcs_client import SkyTrackGCSClient
from skytrack_mcp.clients.storage_sync import (
    list_all_missions,
    read_mission_details,
    resolve_mission_dir,
    write_python_script,
    write_visual_route,
)
from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.diagnostics.healthcheck import run_full_system_healthcheck
from skytrack_mcp.diagnostics.recovery import attempt_system_recovery
from skytrack_mcp.mission.models import CanonicalMission, Waypoint
from skytrack_mcp.mission.parser import canonical_to_ui_dicts, parse_ui_mission
from skytrack_mcp.mission.patcher import MissionPatcher
from skytrack_mcp.mission.validator import (
    VEHICLE_CAPABILITIES,
    validate_canonical_mission,
)
from skytrack_mcp.report.parser import (
    harvest_mission_report_data,
    render_markdown_flight_report,
)
from skytrack_mcp.report.verification import evaluate_mission_requirements
from skytrack_mcp.route.coverage import plan_boustrophedon_coverage
from skytrack_mcp.simulation.observer import observe_simulation_execution
from skytrack_mcp.simulation.runner import (
    execute_canonical_mission,
    send_direct_flight_command,
)
from skytrack_mcp.ui.computer_use import (
    capture_skytrack_screenshot,
    click_relative,
    send_key_name,
    send_keystrokes,
)
from skytrack_mcp.ui.window import (
    focus_skytrack_window,
    get_skytrack_window_bounds,
    is_skytrack_running,
)

_gcs = SkyTrackGCSClient()


# ---------------------------------------------------------------------
# 1. Environment / Application
# ---------------------------------------------------------------------


def tool_skytrack_status() -> Dict[str, Any]:
    """Check running state of SkyTrack app, processes, and ports."""
    running = is_skytrack_running()
    bounds = get_skytrack_window_bounds() if running else None
    sim_health = get_simulation_health()
    return {
        "app_running": running,
        "window_bounds": bounds,
        "docker_ready": sim_health["all_healthy"],
        "containers_running": sum(1 for c in sim_health["containers"].values() if c.get("running")),
        "total_containers": len(sim_health["containers"]),
    }


def tool_skytrack_launch() -> Dict[str, Any]:
    """Launch SkyTrack application if not already running."""
    if is_skytrack_running():
        focus_skytrack_window()
        return {"status": "already_running"}
    subprocess.run(["open", "-a", "SkyTrack"], check=False)
    time.sleep(2.0)
    return {"status": "launched", "running": is_skytrack_running()}


def tool_skytrack_focus() -> Dict[str, Any]:
    """Bring SkyTrack window to the foreground."""
    return focus_skytrack_window()


def tool_skytrack_get_version() -> Dict[str, str]:
    """Get SkyTrack product and runtime version information."""
    return {
        "product_version": "1.2.2",
        "electron_version": "39.8.10",
        "platform": "darwin-arm64",
        "mcp_adapter_version": "0.1.0",
    }


async def tool_skytrack_get_context() -> Dict[str, Any]:
    """Get complete active context: active project, mission, world, vehicle, simulation readiness."""
    missions = list_all_missions()
    active_m = missions[0] if missions else None
    sim_health = get_simulation_health()
    telem = fetch_live_mavlink_telemetry()
    return {
        "active_mission": active_m,
        "selected_world": active_m.get("world") if active_m else "default",
        "selected_vehicle": active_m.get("vehicle") if active_m else "x500_livox_mid_360",
        "simulation_running": sim_health["all_healthy"],
        "telemetry_connected": telem.get("connected", False),
        "drone_landed_state": telem.get("landed_state"),
        "active_project_id": active_m.get("project_id") if active_m else None,
        "active_mission_id": active_m.get("mission_id") if active_m else None,
    }


async def tool_skytrack_healthcheck() -> Dict[str, Any]:
    """Run full diagnostic health check across all SkyTrack integration surfaces."""
    return await run_full_system_healthcheck()


# ---------------------------------------------------------------------
# 2. Projects / Missions
# ---------------------------------------------------------------------


def tool_skytrack_list_projects() -> List[Dict[str, Any]]:
    """List all projects for the authenticated user from SkyTrack Cloud API."""
    return list_cloud_projects()


def tool_skytrack_list_missions(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all local and cached SkyTrack missions, optionally filtered by project_id."""
    all_m = list_all_missions()
    if project_id:
        clean_prj = project_id.removeprefix("prj-")
        return [m for m in all_m if m["project_id"] == clean_prj]
    return all_m


def tool_skytrack_open_mission(mission_id: str) -> Dict[str, Any]:
    """Open and load details for a mission by mission_id."""
    return read_mission_details(mission_id=mission_id)


def tool_skytrack_create_mission(
    name: str,
    project_id: str,
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a mission on Cloud and initialize local ClientData cache."""
    clean_prj = project_id.removeprefix("prj-")
    cloud_res = create_cloud_mission(
        name=name,
        project_id=clean_prj,
        world=world,
        actions=actions or [],
    )
    new_id = str(cloud_res.get("id") or "").removeprefix("mis-")
    local_sync = write_visual_route(
        waypoints=actions or [],
        mission_id=new_id,
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=2.5,
        world=world,
        vehicle=vehicle,
    )
    return {
        "cloud_mission": cloud_res,
        "local_cache": local_sync,
    }


def tool_skytrack_clone_mission(
    source_mission_id: str,
    new_name: str,
    target_project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Clone an existing mission into a new one with a recoverable copy."""
    src = read_mission_details(source_mission_id)
    prj_id = target_project_id or src["project_id"]
    actions = src.get("plan", {}).get("sequences", [{}])[0].get("actions", [])
    meta = src.get("mission", {})

    return tool_skytrack_create_mission(
        name=new_name,
        project_id=prj_id,
        world=meta.get("world", "default"),
        vehicle=meta.get("vehicle", "x500_livox_mid_360"),
        actions=actions,
        spawn_location=src.get("plan", {}).get("spawnLocation"),
    )


def tool_skytrack_export_mission(mission_id: str) -> Dict[str, Any]:
    """Export complete mission JSON payload and script for backup or sharing."""
    return read_mission_details(mission_id=mission_id)


def tool_skytrack_import_mission(
    project_id: str,
    mission_name: str,
    mission_json_content: str,
) -> Dict[str, Any]:
    """Import a raw mission JSON payload into a project."""
    data = json.loads(mission_json_content)
    world = data.get("world", "default")
    vehicle = data.get("vehicle", "x500_livox_mid_360")
    actions = data.get("plan", {}).get("sequences", [{}])[0].get("actions", [])
    return tool_skytrack_create_mission(
        name=mission_name,
        project_id=project_id,
        world=world,
        vehicle=vehicle,
        actions=actions,
    )


# ---------------------------------------------------------------------
# 3. Mission Structured Access
# ---------------------------------------------------------------------


def tool_skytrack_get_mission(mission_id: Optional[str] = None) -> CanonicalMission:
    """Get canonical, strongly-typed mission object."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    patcher = MissionPatcher(mis_dir)
    return patcher.load_canonical()


def tool_skytrack_get_mission_json(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Get raw plan.json and mission.json dicts."""
    return read_mission_details(mission_id=mission_id)


def tool_skytrack_validate_mission(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Run static pre-flight validation against active or specified mission."""
    canonical = tool_skytrack_get_mission(mission_id=mission_id)
    res = validate_canonical_mission(canonical)
    return res.model_dump()


def tool_skytrack_patch_mission(
    patches: Dict[str, Any],
    mission_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Safely apply atomic, snapshot-backed patches to a mission."""
    mis_dir, _, _ = resolve_mission_dir(mission_id)
    patcher = MissionPatcher(mis_dir)
    patched_mission, snapshot_id = patcher.patch_mission(patches)
    validation = validate_canonical_mission(patched_mission)
    return {
        "patched": True,
        "snapshot_id": snapshot_id,
        "validation": validation.model_dump(),
        "mission": patched_mission.model_dump(),
    }


def tool_skytrack_set_mission(
    waypoints: List[Dict[str, Any]],
    mission_id: Optional[str] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: Optional[str] = None,
    vehicle: Optional[str] = None,
) -> Dict[str, Any]:
    """Set entire visual route and mission metadata."""
    return write_visual_route(
        waypoints=waypoints,
        mission_id=mission_id,
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        safety_option=safety_option,
        end_action=end_action,
        world=world,
        vehicle=vehicle,
    )


def tool_skytrack_save_mission(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a persistent snapshot checkpoint of the active mission."""
    mis_dir, _, _ = resolve_mission_dir(mission_id)
    patcher = MissionPatcher(mis_dir)
    snap_id = patcher.create_snapshot()
    return {"saved": True, "snapshot_id": snap_id}


# ---------------------------------------------------------------------
# 4. World / Environment
# ---------------------------------------------------------------------


def tool_skytrack_list_worlds() -> List[str]:
    """List all available Gazebo 3D simulation worlds."""
    return list_gazebo_worlds()


def tool_skytrack_select_world(world_name: str, mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Set world on the active mission and configure simulation."""
    return tool_skytrack_patch_mission({"world": world_name}, mission_id=mission_id)


def tool_skytrack_get_world_context(world_name: Optional[str] = None) -> Dict[str, Any]:
    """Get metadata, spherical coordinates, and obstacle count for a world."""
    if not world_name:
        missions = list_all_missions()
        world_name = missions[0].get("world", "default") if missions else "default"
    data = inspect_world_sdf(world_name)
    return {
        "world": world_name,
        "spherical_coordinates": data.get("spherical_coordinates"),
        "total_obstacles": data.get("total_collision_boxes"),
        "models_count": len(data.get("included_models", [])),
    }


def tool_skytrack_inspect_world(
    world_name: str = "warehouse",
    slice_altitude_m: float = 2.5,
    grid_half_size_m: float = 15.0,
    grid_resolution: int = 31,
) -> Dict[str, Any]:
    """Inspect world obstacles, bounds, and generate 2D top-down ASCII map slice."""
    return inspect_world_sdf(
        world_name=world_name,
        slice_altitude_m=slice_altitude_m,
        grid_half_size_m=grid_half_size_m,
        grid_resolution=grid_resolution,
    )


def tool_skytrack_capture_world(file_path: Optional[str] = None) -> Dict[str, Any]:
    """Capture a visual snapshot of the SkyTrack 3D world view."""
    return capture_skytrack_screenshot(file_path=file_path)


# ---------------------------------------------------------------------
# 5. Vehicle
# ---------------------------------------------------------------------


def tool_skytrack_list_vehicles() -> Dict[str, Any]:
    """List all supported drone models, tags, and payload capabilities."""
    return {"vehicles": VEHICLE_CAPABILITIES}


def tool_skytrack_select_vehicle(vehicle_model: str, mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Select drone vehicle model for a mission."""
    if vehicle_model not in VEHICLE_CAPABILITIES:
        raise SkyTrackError(
            SkyTrackErrorCode.VEHICLE_NOT_FOUND,
            f"Vehicle '{vehicle_model}' not recognized. Available: {list(VEHICLE_CAPABILITIES.keys())}",
        )
    return tool_skytrack_patch_mission({"vehicle": vehicle_model}, mission_id=mission_id)


def tool_skytrack_get_vehicle_context(vehicle_model: Optional[str] = None) -> Dict[str, Any]:
    """Get specifications and payload limits for a vehicle model."""
    if not vehicle_model:
        missions = list_all_missions()
        vehicle_model = missions[0].get("vehicle", "x500_livox_mid_360") if missions else "x500_livox_mid_360"
    v_info = VEHICLE_CAPABILITIES.get(vehicle_model, {})
    return {
        "vehicle": vehicle_model,
        "capabilities": v_info,
    }


# ---------------------------------------------------------------------
# 6. UI / Computer Use
# ---------------------------------------------------------------------


def tool_ui_snapshot(file_path: Optional[str] = None) -> Dict[str, Any]:
    """Capture a screenshot of the SkyTrack application window."""
    return capture_skytrack_screenshot(file_path=file_path)


def tool_ui_click(rel_x: float, rel_y: float) -> Dict[str, Any]:
    """Click at normalized coordinates [0.0 .. 1.0] inside the SkyTrack window."""
    return click_relative(rel_x, rel_y)


def tool_ui_type(text: str) -> Dict[str, Any]:
    """Type text into active focused element."""
    return send_keystrokes(text)


def tool_ui_key(key_name: str) -> Dict[str, Any]:
    """Press a key (return, escape, tab, space, up, down)."""
    return send_key_name(key_name)


def tool_ui_get_state() -> Dict[str, Any]:
    """Get window bounds and foreground status."""
    running = is_skytrack_running()
    bounds = get_skytrack_window_bounds() if running else None
    return {
        "running": running,
        "window_bounds": bounds,
    }


# ---------------------------------------------------------------------
# 7. Simulation Control & Runner
# ---------------------------------------------------------------------


def tool_skytrack_simulation_start(
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    spawn_pose: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Boot simulation stack containers."""
    return start_simulation_stack(world=world, vehicle=vehicle, spawn_pose=spawn_pose)


def tool_skytrack_simulation_stop() -> Dict[str, Any]:
    """Stop the simulation stack."""
    return stop_simulation_stack()


def tool_skytrack_simulation_restart(world: Optional[str] = None) -> Dict[str, Any]:
    """Restart the simulation environment."""
    stop_simulation_stack()
    time.sleep(1.0)
    return start_simulation_stack(world=world or "default")


def tool_skytrack_simulation_state() -> Dict[str, Any]:
    """Get live telemetry, flight mode, and armed status."""
    return fetch_live_mavlink_telemetry()


async def tool_skytrack_simulation_observe(
    max_duration_s: float = 120.0,
    poll_interval_s: float = 3.0,
) -> Dict[str, Any]:
    """Continuously observe live flight progress until landed safely or timeout."""
    return await observe_simulation_execution(
        max_duration_s=max_duration_s,
        poll_interval_s=poll_interval_s,
    )


# ---------------------------------------------------------------------
# 8. Reports & Verification
# ---------------------------------------------------------------------


def tool_skytrack_report_read(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Read structured mission execution report data and markdown report."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    data = harvest_mission_report_data(mis_id, prj_id)
    md = render_markdown_flight_report(data)
    return {
        "report": data,
        "markdown_report": md,
    }


def tool_skytrack_report_export(
    mission_id: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Export flight report to disk."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    target = Path(output_dir) if output_dir else mis_dir
    target.mkdir(parents=True, exist_ok=True)

    data = harvest_mission_report_data(mis_id, prj_id)
    md = render_markdown_flight_report(data)

    (target / "flight_report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (target / "flight_report.md").write_text(md, encoding="utf-8")

    return {
        "exported": True,
        "folder": str(target),
        "files": ["flight_report.json", "flight_report.md"],
    }


def tool_skytrack_verify_mission_requirements(
    requirements: List[Dict[str, Any]],
    mission_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run requirement-by-requirement verification matrix against flight report."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    data = harvest_mission_report_data(mis_id, prj_id)
    matrix = evaluate_mission_requirements(mis_id, requirements, data)
    return matrix.model_dump()


# ---------------------------------------------------------------------
# 9. Diagnostics & Recovery
# ---------------------------------------------------------------------


def tool_skytrack_logs(tail_lines: int = 80) -> Dict[str, Any]:
    """Read onboard execution logs from autonomy container."""
    return read_uav_python_logs(tail_lines=tail_lines)


def tool_skytrack_docker_status() -> Dict[str, Any]:
    """Inspect all SkyTrack container health states."""
    return get_simulation_health()


async def tool_skytrack_diagnostics() -> Dict[str, Any]:
    """Run comprehensive system diagnostics."""
    return await run_full_system_healthcheck()


async def tool_skytrack_recover(issue_type: str = "auto") -> Dict[str, Any]:
    """Execute automated self-healing recovery routines."""
    return await attempt_system_recovery(issue_type=issue_type)
