"""Standardized MCP tool handlers grouped across all SkyTrack capability layers."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skytrack_mcp.clients.cloud_client import (
    create_cloud_mission,
    list_cloud_projects,
)
from skytrack_mcp.clients.docker_exec import (
    fetch_live_mavlink_telemetry,
    get_simulation_health,
    get_simulation_runtime_config,
    inspect_world_sdf,
    list_gazebo_worlds,
    read_uav_python_logs,
    start_simulation_stack,
    stop_simulation_stack,
)
from skytrack_mcp.clients.gcs_client import SkyTrackGCSClient
from skytrack_mcp.clients.storage_sync import (
    list_all_missions,
    read_mission_details,
    resolve_mission_dir,
    switch_mission_mode,
    write_python_script,
    write_visual_route,
)
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.diagnostics.healthcheck import run_full_system_healthcheck
from skytrack_mcp.diagnostics.recovery import attempt_system_recovery
from skytrack_mcp.mission.models import CanonicalMission
from skytrack_mcp.mission.patcher import MissionPatcher
from skytrack_mcp.mission.target import (
    TargetResolutionResult,
    TargetResolutionStatus,
    fetch_cloud_mission_catalog,
    list_project_and_mission_catalog,
    resolve_exact_target,
)
from skytrack_mcp.mission.validator import (
    VEHICLE_CAPABILITIES,
    validate_canonical_mission,
)
from skytrack_mcp.report.parser import (
    harvest_mission_report_data,
    render_markdown_flight_report,
)
from skytrack_mcp.report.verification import evaluate_mission_requirements
from skytrack_mcp.session.auth import (
    detect_installed_app_version,
    probe_app_build_compatibility,
    verify_project_edit_permission,
)
from skytrack_mcp.simulation.observer import observe_simulation_execution
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


def tool_skytrack_status(include_local_docker: bool = False) -> dict[str, Any]:
    """Check running state of SkyTrack desktop application."""
    running = is_skytrack_running()
    bounds = get_skytrack_window_bounds() if running else None
    res: dict[str, Any] = {
        "app_running": running,
        "window_bounds": bounds,
        "simulation_execution": "USER_RUN_REQUIRED",
    }
    if include_local_docker:
        sim_health = get_simulation_health()
        res.update(
            {
                "docker_ready": sim_health["all_healthy"],
                "containers_running": sum(1 for c in sim_health["containers"].values() if c.get("running")),
                "total_containers": len(sim_health["containers"]),
            }
        )
    return res


def tool_skytrack_launch() -> dict[str, Any]:
    """Launch SkyTrack application if not already running."""
    if is_skytrack_running():
        focus_skytrack_window()
        return {"status": "already_running"}
    subprocess.run(["open", "-a", "SkyTrack"], check=False)
    time.sleep(2.0)
    return {"status": "launched", "running": is_skytrack_running()}


def tool_skytrack_focus() -> dict[str, Any]:
    """Bring SkyTrack window to the foreground."""
    return focus_skytrack_window()


def tool_skytrack_get_version() -> dict[str, Any]:
    """Get SkyTrack product and runtime version information dynamically."""
    import platform as py_platform
    import sys

    bundle_v = detect_installed_app_version()
    compat = probe_app_build_compatibility(bundle_version=bundle_v)
    return {
        "bundle_version": bundle_v or "UNKNOWN",
        "app_compatibility": compat["status"],
        "platform": f"{sys.platform}-{py_platform.machine()}",
        "mcp_adapter_version": "0.2.0",
    }


async def tool_skytrack_get_context() -> dict[str, Any]:
    """Get the most recently modified mission and running simulator configuration."""
    missions = list_all_missions()
    active_m = missions[0] if missions else None
    sim_health = get_simulation_health()
    telem = fetch_live_mavlink_telemetry()
    runtime = get_simulation_runtime_config() if sim_health["all_healthy"] else {}
    return {
        "active_mission": active_m,
        "mission_selection_source": "most_recent_modified" if active_m else "none",
        "selected_world": runtime.get("world"),
        "selected_vehicle": runtime.get("vehicle"),
        "simulation_running": sim_health["all_healthy"],
        "telemetry_connected": telem.get("connected", False),
        "drone_landed_state": telem.get("landed_state"),
        "active_project_id": active_m.get("project_id") if active_m else None,
        "active_mission_id": active_m.get("mission_id") if active_m else None,
    }


async def tool_skytrack_healthcheck() -> dict[str, Any]:
    """Run full diagnostic health check across all SkyTrack integration surfaces."""
    return await run_full_system_healthcheck()


# ---------------------------------------------------------------------
# 2. Projects / Missions
# ---------------------------------------------------------------------


def tool_skytrack_list_projects() -> list[dict[str, Any]]:
    """List all projects for the authenticated user from SkyTrack Cloud API."""
    return list_cloud_projects()


def tool_skytrack_resolve_target(
    project_name_or_id: str | None = None,
    mission_name_or_id: str | None = None,
) -> dict[str, Any]:
    """Resolve user-visible project and mission names or IDs to exact, unambiguous IDs."""
    return resolve_exact_target(
        project_name_or_id=project_name_or_id,
        mission_name_or_id=mission_name_or_id,
        catalog_provider=fetch_cloud_mission_catalog,
    ).to_dict()


def tool_skytrack_check_permission(
    project_id: str,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Verify whether the current SkyTrack Desktop session has verified edit rights for a target."""
    return verify_project_edit_permission(
        project_id=project_id,
        mission_id=mission_id,
    ).to_dict()


_DEFAULT_CATALOG_PROVIDER: Callable[[Path], list[dict[str, Any]]] | None = fetch_cloud_mission_catalog


def _active_catalog_provider(data_dir: Path) -> Callable[[Path], list[dict[str, Any]]] | None:
    """Return active catalog provider; enforces cloud catalog by default across all platforms and custom roots.

    Local offline cache inspection requires explicit opt-in via SKYTRACK_OFFLINE_PROFILE=1.
    """
    import os

    if _DEFAULT_CATALOG_PROVIDER is not fetch_cloud_mission_catalog:
        return _DEFAULT_CATALOG_PROVIDER
    if os.environ.get("SKYTRACK_OFFLINE_PROFILE") == "1":
        return None
    return fetch_cloud_mission_catalog


def tool_skytrack_list_missions(project_id: str | None = None) -> list[dict[str, Any]]:
    """List missions for the current authenticated account and local cache.

    Strictly isolates the authenticated account: local orphan directories from other accounts
    are never exposed.
    """
    from skytrack_mcp.clients import storage_sync

    data_dir = storage_sync.CLIENT_DATA_DIR
    provider = _active_catalog_provider(data_dir)
    catalog, catalog_failed = list_project_and_mission_catalog(
        client_data_dir=data_dir,
        catalog_provider=provider,
    )
    if catalog_failed:
        return [
            {
                "status": "UNAVAILABLE",
                "error": "SkyTrack Cloud session catalog is unavailable. Access to local cache directories is blocked when account ownership cannot be verified.",
            }
        ]
    if project_id:
        clean_prj = project_id.removeprefix("prj-").strip()
        return [m for m in catalog if m.get("project_id") == clean_prj]
    return catalog


def _resolve_read_target(
    mission_id: str,
    project_id: str | None = None,
) -> TargetResolutionResult:
    """Resolve and authenticate a target for read/validation operations.

    Guarantees that the mission belongs to the authenticated user's account before
    reading any local file artifacts.
    """
    from skytrack_mcp.clients import storage_sync

    data_dir = storage_sync.CLIENT_DATA_DIR
    provider = _active_catalog_provider(data_dir)
    return resolve_exact_target(
        client_data_dir=data_dir,
        project_name_or_id=project_id,
        mission_name_or_id=mission_id,
        catalog_provider=provider,
    )


def tool_skytrack_open_mission(
    mission_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Open and load details for a mission by mission_id and optional project_id."""
    if not mission_id or not mission_id.strip():
        raise ValueError("Explicit mission_id is required. Inferred or most-recent fallback is prohibited.")

    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": (
                "ARTIFACT_NOT_CACHED: Mission exists in SkyTrack Cloud account but local artifact files "
                "are not yet cached on disk. Open the mission in SkyTrack Desktop to download its visual plan and script."
            ),
        }

    return read_mission_details(mission_id=target.mission_id, project_id=target.project_id)


def tool_skytrack_author_plan(
    project_id: str,
    mission_id: str,
    waypoints: list[dict[str, Any]],
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: str | None = None,
    vehicle: str | None = None,
) -> dict[str, Any]:
    """Author or update visual Plan waypoints for an exact existing mission with verified permissions."""
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": "ARTIFACT_NOT_CACHED: Open the mission in SkyTrack Desktop first.",
        }

    from skytrack_mcp.session.auth import EditAuthorizationStatus, verify_project_edit_permission

    perm = verify_project_edit_permission(project_id=target.project_id, mission_id=target.mission_id)
    if perm.edit_authorization != EditAuthorizationStatus.VERIFIED:
        return {
            "status": "PERMISSION_UNVERIFIED",
            "error": f"Edit permission unverified ({perm.reason}); file write refused.",
            "permission": perm.to_dict(),
        }

    write_res = write_visual_route(
        waypoints=waypoints,
        mission_id=target.mission_id,
        project_id=target.project_id,
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        safety_option=safety_option,
        end_action=end_action,
        world=world,
        vehicle=vehicle,
    )
    return {
        "status": "SUCCESS",
        "persistence": "SAVED_AND_READ_BACK",
        "project_id": target.project_id,
        "mission_id": target.mission_id,
        "refresh_instruction": "Reopen or refresh the mission in SkyTrack Desktop to view updated plan waypoints.",
        "details": write_res,
    }


def tool_skytrack_author_code(
    project_id: str,
    mission_id: str,
    python_code: str,
    switch_to_code_mode: bool = True,
) -> dict[str, Any]:
    """Author or update Python autonomy script.py for an exact mission with verified permissions."""
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": "ARTIFACT_NOT_CACHED: Open the mission in SkyTrack Desktop first.",
        }

    from skytrack_mcp.session.auth import EditAuthorizationStatus, verify_project_edit_permission

    perm = verify_project_edit_permission(project_id=target.project_id, mission_id=target.mission_id)
    if perm.edit_authorization != EditAuthorizationStatus.VERIFIED:
        return {
            "status": "PERMISSION_UNVERIFIED",
            "error": f"Edit permission unverified ({perm.reason}); file write refused.",
            "permission": perm.to_dict(),
        }

    from skytrack_mcp.autonomy_sdk import validate_uav_python_code

    validation = validate_uav_python_code(python_code)

    write_res = write_python_script(
        python_code=python_code,
        mission_id=target.mission_id,
        project_id=target.project_id,
        switch_to_code_mode=switch_to_code_mode,
    )
    return {
        "status": "SUCCESS",
        "persistence": "SAVED_AND_READ_BACK",
        "project_id": target.project_id,
        "mission_id": target.mission_id,
        "validation": validation,
        "refresh_instruction": "Reopen or refresh the mission in SkyTrack Desktop to view updated script.",
        "details": write_res,
    }


def tool_skytrack_switch_mode(
    project_id: str,
    mission_id: str,
    code_mode: bool,
) -> dict[str, Any]:
    """Switch an exact mission between Plan Mode (code_mode=False) and Code Mode (code_mode=True)."""
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": "ARTIFACT_NOT_CACHED: Open the mission in SkyTrack Desktop first.",
        }

    from skytrack_mcp.session.auth import EditAuthorizationStatus, verify_project_edit_permission

    perm = verify_project_edit_permission(project_id=target.project_id, mission_id=target.mission_id)
    if perm.edit_authorization != EditAuthorizationStatus.VERIFIED:
        return {
            "status": "PERMISSION_UNVERIFIED",
            "error": f"Edit permission unverified ({perm.reason}); mode switch refused.",
            "permission": perm.to_dict(),
        }

    return switch_mission_mode(
        mission_id=target.mission_id,
        project_id=target.project_id,
        code_mode=code_mode,
    )


def tool_skytrack_debug_mission(
    project_id: str,
    mission_id: str,
    execution_id: str | None = None,
    user_supplied_logs: str | None = None,
    user_supplied_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect and diagnose an exact mission run from native reports, logs, and media."""
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }

    from skytrack_mcp.report.debug import inspect_mission_run_evidence

    return inspect_mission_run_evidence(
        project_id=target.project_id,
        mission_id=target.mission_id,
        execution_id=execution_id,
        user_supplied_logs=user_supplied_logs,
        user_supplied_report=user_supplied_report,
    )


def tool_skytrack_evaluate_semifinal_2026(
    flight_altitude_agl_m: float | None = None,
    spray_altitude_agl_m: float | None = None,
    residential_clearance_m: float | None = None,
    landing_only_pad_approach: bool | None = None,
    charging_pad_id: str | None = None,
    touchdown_distance_m: float | None = None,
    pad_identity_verified: bool | None = None,
    sprayed_in_residential_buffer: bool | None = None,
    flight_duration_s: float | None = None,
    total_mission_duration_s: float | None = None,
    model_id: str | None = None,
    model_available_in_runtime: bool | None = None,
    perception_correlated: bool | None = None,
) -> dict[str, Any]:
    """Evaluate 2026 Semifinal agricultural mission constraints and physics."""
    from skytrack_mcp.scenarios.semifinal_2026 import (
        MODEL_CLASSES,
        MODEL_ID,
        MODEL_ONNX_SHA256,
        MODEL_ZIP_SHA256,
        VEHICLE_MODEL,
        WORLD_NAME,
        evaluate_semifinal_compliance,
    )

    return evaluate_semifinal_compliance(
        world=WORLD_NAME,
        vehicle=VEHICLE_MODEL,
        flight_altitude_m=flight_altitude_agl_m,
        spray_altitude_m=spray_altitude_agl_m,
        residential_clearance_m=residential_clearance_m,
        landing_only_pad_approach=landing_only_pad_approach,
        charging_pad_id=charging_pad_id,
        touchdown_distance_m=touchdown_distance_m,
        pad_identity_verified=pad_identity_verified,
        sprayed_in_residential_buffer=sprayed_in_residential_buffer,
        flight_duration_s=flight_duration_s,
        total_mission_duration_s=total_mission_duration_s,
        model_catalogue_available=model_available_in_runtime,
        model_id=model_id or (MODEL_ID if model_available_in_runtime else None),
        model_classes=MODEL_CLASSES if model_available_in_runtime else None,
        model_zip_sha256=MODEL_ZIP_SHA256 if model_available_in_runtime else None,
        model_onnx_sha256=MODEL_ONNX_SHA256 if model_available_in_runtime else None,
        perception_verified=perception_correlated,
    )


def tool_skytrack_create_mission(
    name: str,
    project_id: str,
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    actions: list[dict[str, Any]] | None = None,
    spawn_location: list[float] | None = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
) -> dict[str, Any]:
    """Create a mission on Cloud (with v2 schema) and initialize local ClientData cache."""
    clean_prj = project_id.removeprefix("prj-")
    cloud_res = create_cloud_mission(
        name=name,
        project_id=clean_prj,
        world=world,
        vehicle=vehicle,
        actions=actions or [],
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
    )
    new_id = str(cloud_res.get("id") or "").removeprefix("mis-")
    local_sync = write_visual_route(
        waypoints=actions or [],
        mission_id=new_id,
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        world=world,
        vehicle=vehicle,
        project_id=clean_prj,
    )
    return {
        "cloud_mission": cloud_res,
        "local_cache": local_sync,
    }


def tool_skytrack_clone_mission(
    source_mission_id: str,
    new_name: str,
    target_project_id: str | None = None,
) -> dict[str, Any]:
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


def tool_skytrack_export_mission(mission_id: str, project_id: str | None = None) -> dict[str, Any]:
    """Export complete mission JSON payload and script for backup or sharing."""
    return read_mission_details(mission_id=mission_id, project_id=project_id)


def tool_skytrack_import_mission(
    project_id: str,
    mission_name: str,
    mission_json_content: str,
) -> dict[str, Any]:
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


def tool_skytrack_get_mission(
    mission_id: str,
    project_id: str | None = None,
) -> CanonicalMission:
    """Get canonical, strongly-typed mission object."""
    if not mission_id or not mission_id.strip():
        raise ValueError("Explicit mission_id is required. Inferred or most-recent fallback is prohibited.")
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        raise SkyTrackError(
            SkyTrackErrorCode.PERMISSION_DENIED,
            target.error_message or "SkyTrack session catalog is unavailable.",
        )
    if target.status == TargetResolutionStatus.AMBIGUOUS:
        raise ValueError(target.error_message or f"Ambiguous mission_id '{mission_id}'")
    if target.status != TargetResolutionStatus.EXACT:
        raise SkyTrackError(
            SkyTrackErrorCode.PERMISSION_DENIED,
            f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        )
    if not target.cached_locally or not target.path:
        raise SkyTrackError(
            SkyTrackErrorCode.MISSION_NOT_FOUND,
            f"ARTIFACT_NOT_CACHED: Mission '{mission_id}' exists in SkyTrack Cloud account but local artifacts are not cached on disk.",
            suggested_action="Open the mission in SkyTrack Desktop",
        )
    patcher = MissionPatcher(Path(target.path))
    return patcher.load_canonical()


def tool_skytrack_get_mission_json(
    mission_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Get raw plan.json and mission.json dicts."""
    if not mission_id or not mission_id.strip():
        raise ValueError("Explicit mission_id is required. Inferred or most-recent fallback is prohibited.")
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "error": target.error_message}
    if target.status == TargetResolutionStatus.AMBIGUOUS:
        raise ValueError(target.error_message or f"Ambiguous mission_id '{mission_id}'")
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "project_id": project_id,
            "mission_id": mission_id,
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": (
                "ARTIFACT_NOT_CACHED: Mission exists in SkyTrack Cloud account but local artifact files "
                "are not yet cached on disk. Open the mission in SkyTrack Desktop to download its visual plan and script."
            ),
        }
    return read_mission_details(mission_id=target.mission_id, project_id=target.project_id)


def tool_skytrack_validate_mission(
    mission_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Run static pre-flight validation against active or specified mission."""
    if not mission_id or not mission_id.strip():
        raise ValueError("Explicit mission_id is required. Inferred or most-recent fallback is prohibited.")
    target = _resolve_read_target(mission_id, project_id)
    if target.status == TargetResolutionStatus.UNAVAILABLE:
        return {"status": "UNAVAILABLE", "valid": False, "error": target.error_message}
    if target.status == TargetResolutionStatus.AMBIGUOUS:
        raise ValueError(target.error_message or f"Ambiguous mission_id '{mission_id}'")
    if target.status != TargetResolutionStatus.EXACT:
        return {
            "status": "PERMISSION_DENIED",
            "valid": False,
            "project_id": project_id,
            "mission_id": mission_id,
            "error": f"Mission '{mission_id}' does not belong to the active authenticated SkyTrack account.",
        }
    if not target.cached_locally or not target.path:
        return {
            "status": "ARTIFACT_NOT_CACHED",
            "valid": False,
            "project_id": target.project_id,
            "mission_id": target.mission_id,
            "message": (
                "ARTIFACT_NOT_CACHED: Mission exists in SkyTrack Cloud account but local artifact files "
                "are not yet cached on disk. Open the mission in SkyTrack Desktop to download its visual plan and script."
            ),
        }
    patcher = MissionPatcher(Path(target.path))
    canonical = patcher.load_canonical()
    res = validate_canonical_mission(canonical)
    return res.model_dump()


def tool_skytrack_patch_mission(
    patches: dict[str, Any],
    mission_id: str | None = None,
) -> dict[str, Any]:
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
    waypoints: list[dict[str, Any]],
    mission_id: str | None = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: str | None = None,
    vehicle: str | None = None,
) -> dict[str, Any]:
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


def tool_skytrack_save_mission(mission_id: str | None = None) -> dict[str, Any]:
    """Create a persistent snapshot checkpoint of the active mission."""
    mis_dir, _, _ = resolve_mission_dir(mission_id)
    patcher = MissionPatcher(mis_dir)
    snap_id = patcher.create_snapshot()
    return {"saved": True, "snapshot_id": snap_id}


# ---------------------------------------------------------------------
# 4. World / Environment
# ---------------------------------------------------------------------


def tool_skytrack_list_worlds() -> dict[str, Any]:
    """List packaged and cached 3D simulation worlds (.sdf).

    Note: this is an offline packaged SDF reference catalog, not proof of the active world
    in a running simulation.
    """
    return {
        "packaged_worlds": list_gazebo_worlds(),
        "source": "packaged_sdf_reference",
        "active_simulation_world": "UNKNOWN",
    }


def tool_skytrack_select_world(world_name: str, mission_id: str | None = None) -> dict[str, Any]:
    """Set world on the active mission and configure simulation."""
    return tool_skytrack_patch_mission({"world": world_name}, mission_id=mission_id)


def tool_skytrack_get_world_context(
    world_name: str | None = None,
    project_id: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Get metadata, spherical coordinates, and obstacle count for a packaged world.

    Requires explicit world_name or exact (project_id, mission_id). Inferred most-recent fallback is prohibited.
    """
    target_world = world_name
    if not target_world:
        if mission_id:
            target = _resolve_read_target(mission_id, project_id)
            if target.status == TargetResolutionStatus.EXACT and target.cached_locally and target.path:
                details = read_mission_details(mission_id=target.mission_id, project_id=target.project_id)
                meta = details.get("mission", {})
                w_val = meta.get("world", "default")
                target_world = w_val.get("name", "default") if isinstance(w_val, dict) else str(w_val)
            else:
                raise ValueError(
                    f"Cannot infer world from mission '{mission_id}': mission is not cached locally or not in active account."
                )
        else:
            raise ValueError(
                "Explicit world_name or exact (project_id, mission_id) is required. "
                "Inferred most-recent fallback is prohibited."
            )

    data = inspect_world_sdf(target_world)
    return {
        "world": target_world,
        "source": "packaged_sdf_reference",
        "active_simulation_provenance": "UNKNOWN",
        "spherical_coordinates": data.get("spherical_coordinates"),
        "total_obstacles": data.get("total_collision_boxes"),
        "models_count": len(data.get("included_models", [])),
    }


def tool_skytrack_inspect_world(
    world_name: str = "warehouse",
    slice_altitude_m: float = 2.5,
    grid_half_size_m: float = 15.0,
    grid_resolution: int = 31,
) -> dict[str, Any]:
    """Inspect world obstacles, bounds, and generate 2D top-down ASCII map slice."""
    return inspect_world_sdf(
        world_name=world_name,
        slice_altitude_m=slice_altitude_m,
        grid_half_size_m=grid_half_size_m,
        grid_resolution=grid_resolution,
    )


def tool_skytrack_capture_world(file_path: str | None = None) -> dict[str, Any]:
    """Capture a visual snapshot of the SkyTrack 3D world view."""
    return capture_skytrack_screenshot(file_path=file_path)


# ---------------------------------------------------------------------
# 5. Vehicle
# ---------------------------------------------------------------------


def tool_skytrack_list_vehicles() -> dict[str, Any]:
    """List all supported drone models, tags, and payload capabilities."""
    return {"vehicles": VEHICLE_CAPABILITIES}


def tool_skytrack_select_vehicle(vehicle_model: str, mission_id: str | None = None) -> dict[str, Any]:
    """Select drone vehicle model for a mission."""
    if vehicle_model not in VEHICLE_CAPABILITIES:
        raise SkyTrackError(
            SkyTrackErrorCode.VEHICLE_NOT_FOUND,
            f"Vehicle '{vehicle_model}' not recognized. Available: {list(VEHICLE_CAPABILITIES.keys())}",
        )
    return tool_skytrack_patch_mission({"vehicle": vehicle_model}, mission_id=mission_id)


def tool_skytrack_get_vehicle_context(
    vehicle_model: str | None = None,
    project_id: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Get specifications and payload limits for a vehicle model.

    Requires explicit vehicle_model or exact (project_id, mission_id). Inferred most-recent fallback is prohibited.
    """
    target_vehicle = vehicle_model
    if not target_vehicle:
        if mission_id:
            target = _resolve_read_target(mission_id, project_id)
            if target.status == TargetResolutionStatus.EXACT and target.cached_locally and target.path:
                details = read_mission_details(mission_id=target.mission_id, project_id=target.project_id)
                meta = details.get("mission", {})
                v_val = meta.get("vehicle", "x500_livox_mid_360")
                target_vehicle = v_val.get("name", "x500_livox_mid_360") if isinstance(v_val, dict) else str(v_val)
            else:
                raise ValueError(
                    f"Cannot infer vehicle from mission '{mission_id}': mission is not cached locally or not in active account."
                )
        else:
            raise ValueError(
                "Explicit vehicle_model or exact (project_id, mission_id) is required. "
                "Inferred most-recent fallback is prohibited."
            )

    v_info = VEHICLE_CAPABILITIES.get(target_vehicle, {})
    return {
        "vehicle": target_vehicle,
        "capabilities": v_info,
    }


# ---------------------------------------------------------------------
# 6. UI / Computer Use
# ---------------------------------------------------------------------


def tool_ui_snapshot(file_path: str | None = None) -> dict[str, Any]:
    """Capture a screenshot of the SkyTrack application window."""
    return capture_skytrack_screenshot(file_path=file_path)


def tool_ui_click(rel_x: float, rel_y: float) -> dict[str, Any]:
    """Click at normalized coordinates [0.0 .. 1.0] inside the SkyTrack window."""
    return click_relative(rel_x, rel_y)


def tool_ui_type(text: str) -> dict[str, Any]:
    """Type text into active focused element."""
    return send_keystrokes(text)


def tool_ui_key(key_name: str) -> dict[str, Any]:
    """Press a key (return, escape, tab, space, up, down)."""
    return send_key_name(key_name)


def tool_ui_get_state() -> dict[str, Any]:
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
    spawn_pose: list[float] | None = None,
) -> dict[str, Any]:
    """Boot simulation stack containers."""
    return start_simulation_stack(world=world, vehicle=vehicle, spawn_pose=spawn_pose)


def tool_skytrack_simulation_stop() -> dict[str, Any]:
    """Stop the simulation stack."""
    return stop_simulation_stack()


def tool_skytrack_simulation_restart(world: str | None = None) -> dict[str, Any]:
    """Restart the simulation environment."""
    stop_simulation_stack()
    time.sleep(1.0)
    return start_simulation_stack(world=world or "default")


def tool_skytrack_simulation_state() -> dict[str, Any]:
    """Get live telemetry, flight mode, and armed status."""
    return fetch_live_mavlink_telemetry()


async def tool_skytrack_simulation_observe(
    max_duration_s: float = 120.0,
    poll_interval_s: float = 3.0,
) -> dict[str, Any]:
    """Continuously observe live flight progress until landed safely or timeout."""
    return await observe_simulation_execution(
        max_duration_s=max_duration_s,
        poll_interval_s=poll_interval_s,
    )


# ---------------------------------------------------------------------
# 8. Reports & Verification
# ---------------------------------------------------------------------


def tool_skytrack_report_read(
    mission_id: str | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Read structured mission execution report data and markdown report for an optional execution ID."""
    _mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    data = harvest_mission_report_data(mis_id, prj_id, execution_id=execution_id)
    md = render_markdown_flight_report(data)
    return {
        "report": data,
        "markdown_report": md,
    }


def tool_skytrack_report_export(
    mission_id: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
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
    requirements: list[dict[str, Any]],
    mission_id: str | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Run requirement-by-requirement verification matrix against a flight execution."""
    _mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    data = harvest_mission_report_data(mis_id, prj_id, execution_id=execution_id)
    matrix = evaluate_mission_requirements(mis_id, requirements, data)
    return matrix.model_dump()


# ---------------------------------------------------------------------
# 9. Diagnostics & Recovery
# ---------------------------------------------------------------------


def tool_skytrack_logs(tail_lines: int = 80) -> dict[str, Any]:
    """Read onboard execution logs from autonomy container."""
    return read_uav_python_logs(tail_lines=tail_lines)


def tool_skytrack_docker_status() -> dict[str, Any]:
    """Inspect all SkyTrack container health states."""
    return get_simulation_health()


async def tool_skytrack_diagnostics() -> dict[str, Any]:
    """Run comprehensive system diagnostics."""
    return await run_full_system_healthcheck()


async def tool_skytrack_recover(issue_type: str = "auto") -> dict[str, Any]:
    """Execute automated self-healing recovery routines."""
    return await attempt_system_recovery(issue_type=issue_type)
