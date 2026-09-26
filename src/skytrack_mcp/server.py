"""SkyTrack FastMCP Server — Complete Production Implementation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

from skytrack_mcp.clients.cloud_client import (
    call_cloud_api,
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
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.report.parser import (
    harvest_mission_report_data,
    render_markdown_flight_report,
)
from skytrack_mcp.mcp.prompts import get_prompt_templates
from skytrack_mcp.mcp.resources import (
    get_capabilities_resource,
    get_current_mission_resource,
    get_current_report_resource,
    get_errors_catalog_resource,
    get_mission_schema_resource,
    get_operator_guide_resource,
    get_vehicles_resource,
    get_worlds_resource,
)
from skytrack_mcp.mcp.tools import (
    tool_skytrack_clone_mission,
    tool_skytrack_create_mission,
    tool_skytrack_capture_world,
    tool_skytrack_diagnostics,
    tool_skytrack_docker_status,
    tool_skytrack_export_mission,
    tool_skytrack_focus,
    tool_skytrack_get_context,
    tool_skytrack_get_mission,
    tool_skytrack_get_mission_json,
    tool_skytrack_get_vehicle_context,
    tool_skytrack_get_version,
    tool_skytrack_get_world_context,
    tool_skytrack_healthcheck,
    tool_skytrack_import_mission,
    tool_skytrack_inspect_world,
    tool_skytrack_launch,
    tool_skytrack_list_missions,
    tool_skytrack_list_projects,
    tool_skytrack_list_vehicles,
    tool_skytrack_list_worlds,
    tool_skytrack_logs,
    tool_skytrack_open_mission,
    tool_skytrack_patch_mission,
    tool_skytrack_recover,
    tool_skytrack_report_export,
    tool_skytrack_report_read,
    tool_skytrack_save_mission,
    tool_skytrack_select_vehicle,
    tool_skytrack_select_world,
    tool_skytrack_set_mission,
    tool_skytrack_simulation_observe,
    tool_skytrack_simulation_restart,
    tool_skytrack_simulation_start,
    tool_skytrack_simulation_state,
    tool_skytrack_simulation_stop,
    tool_skytrack_status,
    tool_skytrack_validate_mission,
    tool_skytrack_verify_mission_requirements,
    tool_ui_click,
    tool_ui_get_state,
    tool_ui_key,
    tool_ui_snapshot,
    tool_ui_type,
)

mcp = FastMCP(
    "SkyTrack UAV MCP",
    instructions=(
        "Comprehensive MCP integration for SkyTrack Mission Studio. "
        "Allows autonomous AI agents to inspect 3D Gazebo environments, construct and validate "
        "missions, manipulate visual routes and Python autonomy scripts, manage Docker simulation "
        "lifecycles, execute flights, monitor live telemetry, and verify outcomes against mission reports."
    ),
)

_gcs = SkyTrackGCSClient()


# =====================================================================
# MCP RESOURCES (skytrack://...)
# =====================================================================


@mcp.resource("skytrack://docs/operator-guide")
def resource_operator_guide() -> str:
    """SkyTrack autonomous mission operator guide."""
    return get_operator_guide_resource()


@mcp.resource("skytrack://schema/mission")
def resource_mission_schema() -> str:
    """Canonical JSON Schema for SkyTrack missions."""
    return get_mission_schema_resource()


@mcp.resource("skytrack://worlds")
def resource_worlds() -> str:
    """Available Gazebo 3D simulation worlds."""
    return get_worlds_resource()


@mcp.resource("skytrack://vehicles")
def resource_vehicles() -> str:
    """Available drone models, accessories, and capabilities."""
    return get_vehicles_resource()


@mcp.resource("skytrack://errors/catalog")
def resource_errors_catalog() -> str:
    """Standardized error codes catalog for SkyTrack."""
    return get_errors_catalog_resource()


@mcp.resource("skytrack://capabilities")
def resource_capabilities() -> str:
    """SkyTrack MCP server capabilities and adapter features."""
    return get_capabilities_resource()


@mcp.resource("skytrack://current/mission")
def resource_current_mission() -> str:
    """JSON details of the active mission in ClientData."""
    return get_current_mission_resource()


@mcp.resource("skytrack://current/report")
def resource_current_report() -> str:
    """Latest flight report in Markdown for the active mission."""
    return get_current_report_resource()


# =====================================================================
# MCP PROMPTS
# =====================================================================


@mcp.prompt()
def skytrack_solve_mission(assignment: str, world: str = "", vehicle: str = "") -> str:
    """Orchestrates the full Observe -> Plan -> Execute -> Verify autonomous mission workflow."""
    tpl = get_prompt_templates()["skytrack-solve-mission"]["template"]
    return tpl.format(assignment=assignment, world=world or "active", vehicle=vehicle or "active")


@mcp.prompt()
def skytrack_inspect_world_prompt(world_name: str, altitude_m: float = 2.5) -> str:
    """Inspect 3D Gazebo environment, obstacles, racks, and clearance corridors at flight altitude."""
    tpl = get_prompt_templates()["skytrack-inspect-world"]["template"]
    return tpl.format(world_name=world_name, altitude_m=altitude_m)


@mcp.prompt()
def skytrack_debug_mission(mission_id: str = "") -> str:
    """Diagnose a failing or stuck mission, analyze errors, and repair route/code."""
    tpl = get_prompt_templates()["skytrack-debug-mission"]["template"]
    return tpl.format(mission_id=mission_id or "active")


@mcp.prompt()
def skytrack_review_route(world_name: str, waypoints_json: str) -> str:
    """Statically review candidate route waypoints against vehicle limits and 3D terrain."""
    tpl = get_prompt_templates()["skytrack-review-route"]["template"]
    return tpl.format(world_name=world_name, waypoints_json=waypoints_json)


@mcp.prompt()
def skytrack_explain_report(mission_id: str = "") -> str:
    """Analyze an official SkyTrack flight report and provide executive summary."""
    tpl = get_prompt_templates()["skytrack-explain-report"]["template"]
    return tpl.format(mission_id=mission_id or "active")


# =====================================================================
# MCP TOOLS — STANDARDIZED CAPABILITY GROUPS
# =====================================================================

# 1. Environment / Application
mcp.tool()(tool_skytrack_status)
mcp.tool()(tool_skytrack_launch)
mcp.tool()(tool_skytrack_focus)
mcp.tool()(tool_skytrack_get_version)
mcp.tool()(tool_skytrack_get_context)
mcp.tool()(tool_skytrack_healthcheck)

# 2. Projects / Missions
mcp.tool()(tool_skytrack_list_projects)
mcp.tool()(tool_skytrack_list_missions)
mcp.tool()(tool_skytrack_open_mission)
mcp.tool()(tool_skytrack_create_mission)
mcp.tool()(tool_skytrack_clone_mission)
mcp.tool()(tool_skytrack_export_mission)
mcp.tool()(tool_skytrack_import_mission)

# 3. Mission Structured Access
mcp.tool()(tool_skytrack_get_mission)
mcp.tool()(tool_skytrack_get_mission_json)
mcp.tool()(tool_skytrack_validate_mission)
mcp.tool()(tool_skytrack_patch_mission)
mcp.tool()(tool_skytrack_set_mission)
mcp.tool()(tool_skytrack_save_mission)

# 4. World / Environment
mcp.tool()(tool_skytrack_list_worlds)
mcp.tool()(tool_skytrack_select_world)
mcp.tool()(tool_skytrack_get_world_context)
mcp.tool()(tool_skytrack_inspect_world)
mcp.tool()(tool_skytrack_capture_world)

# 5. Vehicle
mcp.tool()(tool_skytrack_list_vehicles)
mcp.tool()(tool_skytrack_select_vehicle)
mcp.tool()(tool_skytrack_get_vehicle_context)

# 6. UI / Computer Use
mcp.tool()(tool_ui_snapshot)
mcp.tool()(tool_ui_click)
mcp.tool()(tool_ui_type)
mcp.tool()(tool_ui_key)
mcp.tool()(tool_ui_get_state)

# 7. Simulation Control & Observation
mcp.tool()(tool_skytrack_simulation_start)
mcp.tool()(tool_skytrack_simulation_stop)
mcp.tool()(tool_skytrack_simulation_restart)
mcp.tool()(tool_skytrack_simulation_state)
mcp.tool()(tool_skytrack_simulation_observe)

# 8. Reports & Verification
mcp.tool()(tool_skytrack_report_read)
mcp.tool()(tool_skytrack_report_export)
mcp.tool()(tool_skytrack_verify_mission_requirements)

# 9. Diagnostics & Recovery
mcp.tool()(tool_skytrack_logs)
mcp.tool()(tool_skytrack_docker_status)
mcp.tool()(tool_skytrack_diagnostics)
mcp.tool()(tool_skytrack_recover)


# =====================================================================
# MCP TOOLS — COMPOSITE CONVENIENCE PRIMITIVES
# =====================================================================


@mcp.tool()
async def list_missions_and_worlds() -> Dict[str, Any]:
    """List all SkyTrack projects and missions in local ClientData along with all available
    3D Gazebo worlds (.sdf) and Path Planner API health status.
    """
    missions = list_all_missions()
    worlds = list_gazebo_worlds()
    try:
        planner_health = await _gcs.get_planner_health()
    except Exception as exc:
        planner_health = {"status": "unreachable", "error": str(exc)}

    return {
        "active_mission": missions[0] if missions else None,
        "missions": missions,
        "available_worlds": worlds,
        "planner_api_health": planner_health,
    }


@mcp.tool()
def get_mission_state(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Read the full state of a SkyTrack mission (mission.json metadata, plan.json visual route,
    and script.py Python code).
    """
    return read_mission_details(mission_id=mission_id)


@mcp.tool()
def inspect_world_map(
    world_name: str = "warehouse",
    slice_altitude_m: float = 2.5,
    grid_half_size_m: float = 15.0,
    grid_resolution: int = 31,
) -> Dict[str, Any]:
    """Inspect a 3D Gazebo world (.sdf) to extract all obstacles/buildings/walls with their
    exact 3D bounding boxes (AABB in ENU meters) and generate a 2D top-down ASCII occupancy map.
    """
    return inspect_world_sdf(
        world_name=world_name,
        slice_altitude_m=slice_altitude_m,
        grid_half_size_m=grid_half_size_m,
        grid_resolution=grid_resolution,
    )


@mcp.tool()
def check_route_collisions(
    world_name: str,
    waypoints: List[List[float]],
    clearance_m: float = 0.4,
) -> Dict[str, Any]:
    """Verify whether a sequence of 3D ENU waypoints `[[x, y, z], ...]` is collision-free against
    all 3D collision geometries in `world_name.sdf`.
    """
    return check_waypoints_collisions(
        world_name=world_name,
        waypoints=waypoints,
        clearance_m=clearance_m,
    )


@mcp.tool()
async def get_uav_telemetry() -> Dict[str, Any]:
    """Fetch real-time UAV telemetry from the MAVLink bridge and GCS action feedback stream."""
    mav_data = fetch_live_mavlink_telemetry()
    gcs_fb = await _gcs.get_gcs_feedback_snapshot()
    return {
        "telemetry": mav_data,
        "gcs_action_feedback": gcs_fb,
    }


@mcp.tool()
async def plan_coverage_route(
    area_coords: List[Dict[str, float]],
    spacing_m: float = 2.0,
    orientation_deg: float = 90.0,
    altitude_m: float = 2.5,
    hole_coords: Optional[List[List[Dict[str, float]]]] = None,
    no_fly_zones: Optional[List[Dict[str, Any]]] = None,
    save_to_mission_ui: bool = True,
    mission_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an optimized zigzag coverage route inside a polygon area using Path Planner API (:20007)."""
    plan_res = await _gcs.plan_coverage_xy(
        area_coords=area_coords,
        spacing=spacing_m,
        orientation=orientation_deg,
        hole_coords=hole_coords,
    )
    vertices = plan_res.get("vertexs", [])
    waypoints_3d: List[List[float]] = [
        [round(float(v["x"]), 3), round(float(v["y"]), 3), round(float(altitude_m), 3)]
        for v in vertices
    ]

    nfz_info = None
    if no_fly_zones and waypoints_3d:
        nfz_info = await _gcs.split_waypoints_nfz(
            waypoints_enu=waypoints_3d,
            nfz_zones=no_fly_zones,
            boundary_margin_m=1.0,
        )
        waypoints_3d = [wp["point"] for wp in nfz_info.get("waypoints", [])]

    ui_sync = None
    if save_to_mission_ui and waypoints_3d:
        wp_dicts = [{"x": pt[0], "y": pt[1], "z": pt[2]} for pt in waypoints_3d]
        ui_sync = write_visual_route(
            waypoints=wp_dicts,
            mission_id=mission_id,
            takeoff_altitude=altitude_m,
        )

    return {
        "waypoint_count": len(waypoints_3d),
        "waypoints_enu": waypoints_3d,
        "nfz_split_summary": nfz_info,
        "saved_to_skytrack_ui": ui_sync is not None,
        "mission_id": ui_sync["mission_id"] if ui_sync else mission_id,
    }


@mcp.tool()
def draw_route_on_map(
    waypoints: List[Dict[str, Any]],
    mission_id: Optional[str] = None,
    spawn_location: Optional[List[float]] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: Optional[str] = None,
    vehicle: Optional[str] = None,
) -> Dict[str, Any]:
    """Draw a visual route directly onto the SkyTrack Map UI (`plan.json` & `mission.json`)."""
    return write_visual_route(
        waypoints=waypoints,
        mission_id=mission_id,
        spawn_location=spawn_location,
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        safety_option=safety_option,
        end_action=end_action,
        world=world,
        vehicle=vehicle,
    )


@mcp.tool()
async def execute_route_mission(
    waypoints: Optional[List[Dict[str, Any]]] = None,
    mission_id: Optional[str] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    avoidance_mode: str = "avoid",
    no_fly_zones: Optional[List[Dict[str, Any]]] = None,
    end_action: str = "rtl",
    also_save_to_ui: bool = True,
) -> Dict[str, Any]:
    """Execute a waypoint route mission on the UAV via GCS API (`POST :20002/mission/v2/execute`)."""
    if waypoints is None:
        details = read_mission_details(mission_id=mission_id)
        plan = details.get("plan", {})
        mission_meta = details.get("mission", {})
        takeoff_altitude = float(mission_meta.get("takeoffAltitude", takeoff_altitude))
        target_speed = float(mission_meta.get("targetSpeed", target_speed))
        avoidance_mode = str(mission_meta.get("safetyOption", avoidance_mode))
        end_action = str(mission_meta.get("end", {}).get("type", end_action))
        sequences = plan.get("sequences", [])
        waypoints = []
        for seq in sequences:
            for act in seq.get("actions", []):
                waypoints.append(act)
        if not waypoints:
            raise ValueError(
                f"No waypoints provided and mission '{details['mission_id']}' has an empty plan.json."
            )
    elif also_save_to_ui:
        write_visual_route(
            waypoints=waypoints,
            mission_id=mission_id,
            takeoff_altitude=takeoff_altitude,
            target_speed=target_speed,
            safety_option=avoidance_mode,
            end_action=end_action,
        )

    return await _gcs.execute_mission_v2(
        waypoints=waypoints,
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        avoidance_mode=avoidance_mode,
        no_fly_zones=no_fly_zones,
        end_action=end_action,
    )


@mcp.tool()
async def control_uav_flight(
    command: str,
    altitude_m: float = 2.5,
    smart: bool = True,
) -> Dict[str, Any]:
    """Send direct flight or mission control commands to the UAV (:20002)."""
    return await send_direct_flight_command(command=command, altitude_m=altitude_m, smart=smart)


@mcp.tool()
def get_uav_python_sdk_reference() -> Dict[str, Any]:
    """Return function signatures, coordinate conventions, and verified templates for SkyTrack Python SDK
    (`GetSkyTrack/skytrack-autonomy-example` develop branch reference).
    """
    return {
        "sdk_module": "local_planner",
        "execution_container": "skytrack-simulation-skytrack-autonomy-1",
        "known_issues_and_rules": [
            "1. Always start with `from __future__ import annotations` and define `UPPER_CASE` mission constants.",
            "2. `takeoff(alt_m=...)` and `fly_to(north=..., east=..., alt_m=...)` require `alt_m` (positive meters up).",
            "3. `fly_to` supports `mode='transit' | 'coverage' | 'direct'` and `replan_mode='fast' | 'slow'`.",
            "4. Always `yield brake()` before `capture()` and before `land()` to eliminate motion blur and overshoot.",
            "5. For video recording, register `drone.add_sense(CameraSense())` and `drone.add_service(VideoRecorder(output_dir='~/.ros/recordings', fps=10.0))`, add `'camera'` to `scenario.requires_senses`, and call `rec = ctx.services.recorder; rec.start(clip='...'); ...; rec.stop()`.",
            "6. `ctx.senses.battery.percent` is on a 0–100 scale (e.g. `20.0` means 20%, NOT `0.20`).",
        ],
        "function_signatures": {
            "boot_drone": "boot_drone() -> ContextManager[Drone]",
            "takeoff": "takeoff(*, alt_m: float = 3.0, name: Optional[str] = None) -> SkillStep",
            "fly_to": "fly_to(x=None, y=None, z=None, *, north: Optional[float] = None, east: Optional[float] = None, alt_m: Optional[float] = None, direct: bool = False, mode: Optional[str] = None, replan_mode: Optional[str] = None, target_speed: Optional[float] = None, name: Optional[str] = None) -> SkillStep",
            "orbit": "orbit(center=None, *, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, radius_m: float = 5.0, period_s: float = 20.0, duration_s: float = 60.0) -> SkillStep",
            "helix": "helix(center=None, *, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, alt_m_end: Optional[float] = None, radius_m: float = 5.0, duration_s: float = 60.0) -> SkillStep",
            "yaw_to": "yaw_to(face=None, *, north: Optional[float] = None, east: Optional[float] = None, name: str = 'yaw_to') -> SkillStep",
            "capture": "capture(*, output_dir: str = '~/.ros/captures', filename: Optional[str] = None) -> SkillStep",
            "brake": "brake(*, name: str = 'brake') -> SkillStep",
            "land": "land(*, name: str = 'land') -> SkillStep",
            "CameraSense": "CameraSense()",
            "VideoRecorder": "VideoRecorder(output_dir: str = '~/.ros/recordings', fps: float = 10.0)",
            "Snapshot": "Snapshot(output_dir: str = '~/.ros/captures')",
            "Sprayer": "Sprayer()",
            "Detector": "Detector(model_name: str = 'yolov8n')",
        },
        "example_script": (
            'from __future__ import annotations\n'
            'from typing import Any, Iterator\n'
            'from local_planner import (\n'
            '    CameraSense,\n'
            '    VideoRecorder,\n'
            '    boot_drone,\n'
            '    brake,\n'
            '    capture,\n'
            '    fly_to,\n'
            '    land,\n'
            '    takeoff,\n'
            ')\n\n'
            'ALTITUDE_M = 2.5\n\n'
            'def scenario(ctx: Any) -> Iterator[Any]:\n'
            '    rec = ctx.services.recorder\n'
            '    yield takeoff(alt_m=ALTITUDE_M)\n'
            '    rec.start(clip="mission_recording")\n'
            '    yield fly_to(north=5.0, east=0.0, alt_m=ALTITUDE_M, mode="transit")\n'
            '    yield brake()\n'
            '    yield capture(filename="wp_1.jpg")\n'
            '    rec.stop()\n'
            '    yield brake()\n'
            '    yield land()\n\n'
            'scenario.requires_senses = ["pose", "obstacle", "status", "camera"]\n\n'
            'def main() -> None:\n'
            '    with boot_drone() as drone:\n'
            '        drone.add_sense(CameraSense())\n'
            '        drone.add_service(VideoRecorder(output_dir="~/.ros/recordings", fps=10.0))\n'
            '        drone.fly(scenario)\n'
            '        drone.run()\n\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
        ),
    }


def validate_uav_python_code(python_code: str) -> Dict[str, Any]:
    """Static AST analyzer for SkyTrack UAV Python scripts."""
    errors: List[str] = []
    warnings: List[str] = []

    try:
        tree = ast.parse(python_code)
    except SyntaxError as exc:
        return {
            "valid": False,
            "errors": [f"SyntaxError at line {exc.lineno}: {exc.msg}"],
            "warnings": [],
        }

    has_boot_drone = False
    has_yield = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            has_yield = True
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name == "boot_drone":
                has_boot_drone = True

            if func_name == "takeoff":
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                if "altitude" in kw_names or "z" in kw_names:
                    errors.append(
                        "takeoff() uses `alt_m=...` keyword argument, not `altitude` or `z`."
                    )

            if func_name == "fly_to":
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                if "altitude" in kw_names:
                    errors.append("fly_to() uses `alt_m=...` keyword argument, not `altitude`.")

    if not has_boot_drone:
        warnings.append("Script does not call `boot_drone()`; ensure it initializes the ROS 2 node.")
    if not has_yield:
        warnings.append("No `yield` statement found; `scenario(ctx)` should yield SkillSteps.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


@mcp.tool()
def convert_route_to_python_script(
    waypoints: Optional[List[Dict[str, Any]]] = None,
    mission_id: Optional[str] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    save_to_mission: bool = True,
) -> Dict[str, Any]:
    """Convert visual waypoints into a runnable SkyTrack Python script following
    `GetSkyTrack/skytrack-autonomy-example` conventions (`CameraSense`, `VideoRecorder`, `brake()`).
    """
    if waypoints is None:
        details = read_mission_details(mission_id=mission_id)
        plan = details.get("plan", {})
        meta = details.get("mission", {})
        takeoff_altitude = float(meta.get("takeoffAltitude", takeoff_altitude))
        target_speed = float(meta.get("targetSpeed", target_speed))
        waypoints = []
        for seq in plan.get("sequences", []):
            for act in seq.get("actions", []):
                waypoints.append(act)

    has_video = any(
        wp.get("type") in ("start-recording-video", "stop-recording-video", "recording_on", "recording_off")
        or wp.get("after_action") in ("start-recording-video", "stop-recording-video", "recording_on", "recording_off")
        for wp in waypoints
    )

    steps: List[str] = []
    if has_video:
        steps.append("    rec = ctx.services.recorder")
    steps.append(f"    yield takeoff(alt_m={takeoff_altitude:.2f})")

    for idx, wp in enumerate(waypoints, start=1):
        wp_type = wp.get("type", "navigate")
        after_act = wp.get("after_action")
        if wp_type in ("navigate", "navigation", "waypoint") or ("x" in wp and "y" in wp):
            if "data" in wp and isinstance(wp["data"], list) and len(wp["data"]) == 3:
                east_x, north_y, alt_z = float(wp["data"][0]), float(wp["data"][1]), float(wp["data"][2])
            else:
                east_x = float(wp.get("x", wp.get("east", 0.0)))
                north_y = float(wp.get("y", wp.get("north", 0.0)))
                alt_z = float(wp.get("z", wp.get("alt_m", takeoff_altitude)))
            steps.append(
                f"    yield fly_to(north={north_y:.3f}, east={east_x:.3f}, alt_m={alt_z:.3f}, target_speed={target_speed:.2f}, name='wp_{idx}')"
            )
            if after_act in ("start-recording-video", "recording_on"):
                steps.append("    rec.start(clip='mission_recording')")
            elif after_act in ("stop-recording-video", "recording_off"):
                steps.append("    rec.stop()")
            elif after_act in ("take-photo", "take-snapshot", "snapshot"):
                steps.append("    yield brake()")
                steps.append(f"    yield capture(filename='wp_{idx}.jpg')")
        elif wp_type in ("start-recording-video", "recording_on"):
            steps.append("    rec.start(clip='mission_recording')")
        elif wp_type in ("stop-recording-video", "recording_off"):
            steps.append("    rec.stop()")
        elif wp_type in ("take-photo", "take-snapshot", "snapshot"):
            steps.append("    yield brake()")
            steps.append(f"    yield capture(filename='step_{idx}.jpg')")

    steps.append("    yield fly_to(north=0.0, east=0.0, alt_m=" + f"{takeoff_altitude:.2f}, name='return_home')")
    steps.append("    yield brake()")
    steps.append("    yield land()")

    body = "\n".join(steps)
    extra_imports = "    CameraSense,\n    VideoRecorder,\n" if has_video else ""
    senses_list = '["pose", "obstacle", "status", "camera"]' if has_video else '["pose", "obstacle", "status"]'
    service_reg = (
        '        drone.add_sense(CameraSense())\n'
        '        drone.add_service(VideoRecorder(output_dir="~/.ros/recordings", fps=10.0))\n'
        if has_video
        else ""
    )

    script_code = f'''"""Auto-generated SkyTrack UAV Python Script from Route Waypoints."""

from __future__ import annotations

from typing import Any, Iterator
from local_planner import (
{extra_imports}    boot_drone,
    takeoff,
    fly_to,
    capture,
    brake,
    land,
)


def scenario(ctx: Any) -> Iterator[Any]:
{body}


scenario.requires_senses = {senses_list}


def main() -> None:
    with boot_drone() as drone:
{service_reg}        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
'''
    save_info = None
    if save_to_mission:
        save_info = write_python_script(
            python_code=script_code,
            mission_id=mission_id,
            switch_to_code_mode=True,
        )

    return {
        "python_code": script_code,
        "saved_info": save_info,
    }


@mcp.tool()
def write_and_save_uav_script(
    python_code: str,
    mission_id: Optional[str] = None,
    switch_to_code_mode: bool = True,
) -> Dict[str, Any]:
    """Validate AST and save code to script.py in target mission directory."""
    validation = validate_uav_python_code(python_code)
    if not validation["valid"]:
        return {"saved": False, "validation": validation}

    saved_info = write_python_script(
        python_code=python_code,
        mission_id=mission_id,
        switch_to_code_mode=switch_to_code_mode,
    )
    return {
        "saved": True,
        "validation": validation,
        **saved_info,
    }


@mcp.tool()
def execute_uav_python_script(
    python_code: Optional[str] = None,
    mission_id: Optional[str] = None,
    background: bool = True,
    wait_seconds: float = 3.5,
) -> Dict[str, Any]:
    """Execute Python script in ROS 2 Jazzy skytrack-autonomy container."""
    if python_code is not None:
        validation = validate_uav_python_code(python_code)
        if not validation["valid"]:
            return {"executed": False, "validation": validation}
        write_python_script(
            python_code=python_code,
            mission_id=mission_id,
            switch_to_code_mode=True,
        )
    else:
        details = read_mission_details(mission_id=mission_id)
        python_code = details.get("script", "")
        if not python_code.strip():
            raise ValueError(f"No script.py content found for mission {details['mission_id']}.")
        validation = validate_uav_python_code(python_code)
        if not validation["valid"]:
            return {"executed": False, "validation": validation}

    exec_result = run_uav_python_in_container(
        python_code=python_code,
        background=background,
        wait_seconds=wait_seconds,
    )
    return {
        "executed": True,
        "validation": validation,
        **exec_result,
    }


@mcp.tool()
def stop_uav_python_script() -> Dict[str, Any]:
    """Stop any currently running Python UAV script in autonomy container."""
    return stop_uav_python_in_container()


@mcp.tool()
def get_uav_script_logs(tail_lines: int = 80) -> Dict[str, Any]:
    """Read logs of Python UAV script inside autonomy container."""
    return read_uav_python_logs(tail_lines=tail_lines)


@mcp.tool()
def list_skytrack_cloud_projects() -> List[Dict[str, Any]]:
    """List all projects for current user from SkyTrack Cloud API."""
    return list_cloud_projects()


@mcp.tool()
def create_mission_on_cloud(
    name: str,
    project_id: str,
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a mission on Cloud and initialize local ClientData cache."""
    return tool_skytrack_create_mission(
        name=name,
        project_id=project_id,
        world=world,
        vehicle=vehicle,
        actions=actions,
        spawn_location=spawn_location,
    )


@mcp.tool()
def sync_mission_to_cloud(mission_id: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """Upload local changes from plan.json and mission.json (including v2 client/mc/metadata) to SkyTrack Cloud."""
    details = read_mission_details(mission_id=mission_id)
    mis_id = details["mission_id"]
    plan = details.get("plan", {})
    mission_meta = details.get("mission", {})
    sequences = plan.get("sequences", [])
    actions = []
    for seq in sequences:
        actions.extend(seq.get("actions", []))

    world_val = mission_meta.get("world", "default")
    if isinstance(world_val, dict):
        world_val = world_val.get("name", "default")

    veh_val = mission_meta.get("vehicle", "x500_livox_mid_360")
    if isinstance(veh_val, dict):
        veh_val = veh_val.get("name", "x500_livox_mid_360")

    cloud_update = update_cloud_mission(
        mission_id=mis_id,
        name=name,
        world=str(world_val),
        vehicle=str(veh_val),
        actions=actions,
        spawn_location=plan.get("spawnLocation"),
        takeoff_altitude=float(mission_meta.get("takeoffAltitude", 2.5)),
        target_speed=float(mission_meta.get("targetSpeed", 2.0)),
        safety_option=str(mission_meta.get("safetyOption", "avoid")),
        end_action=str(mission_meta.get("end", {}).get("type", "rtl")),
    )
    return {
        "synced_mission_id": mis_id,
        "actions_count": len(actions),
        "cloud_response": cloud_update,
    }


@mcp.tool()
def manage_simulation_stack(
    action: str = "status",
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    spawn_pose: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Manage SkyTrack Docker Simulation Stack (action: 'status' | 'start' | 'stop')."""
    act = action.lower().strip()
    if act == "status":
        return get_simulation_health()
    if act == "start":
        return start_simulation_stack(world=world, vehicle=vehicle, spawn_pose=spawn_pose)
    if act == "stop":
        return stop_simulation_stack()
    raise ValueError(f"Unknown action '{action}'. Valid: 'status', 'start', 'stop'.")


@mcp.tool()
async def run_mission_and_wait_completion(
    mission_id: Optional[str] = None,
    waypoints: Optional[List[Dict[str, Any]]] = None,
    poll_interval_s: float = 3.0,
    max_wait_seconds: float = 120.0,
) -> Dict[str, Any]:
    """Closed-loop autonomous flight execution with live polling until safe landing."""
    exec_res = await execute_route_mission(
        waypoints=waypoints,
        mission_id=mission_id,
        also_save_to_ui=True,
    )
    if not exec_res.get("ok"):
        return {"status": "failed_to_dispatch", "error": exec_res.get("response")}

    obs = await observe_simulation_execution(
        max_duration_s=max_wait_seconds,
        poll_interval_s=poll_interval_s,
    )
    return {
        "status": "completed_safely" if obs["completed"] else "timeout_or_failed",
        "observation": obs,
    }


@mcp.tool()
def harvest_flight_report(
    mission_id: Optional[str] = None,
    save_to_disk: bool = True,
) -> Dict[str, Any]:
    """Compile structured flight report and Markdown summary from logs and telemetry."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id)
    data = harvest_mission_report_data(mis_id, prj_id)
    md = render_markdown_flight_report(data)

    if save_to_disk:
        (mis_dir / "flight_report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        (mis_dir / "flight_report.md").write_text(md, encoding="utf-8")

    return {
        "report": data,
        "markdown_report": md,
        "saved_to_folder": str(mis_dir) if save_to_disk else None,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
