"""SkyTrack FastMCP Server — Map Inspection, Visual Route Drawing, and Python UAV Execution."""

from __future__ import annotations

import ast
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
    write_python_script,
    write_visual_route,
)

mcp = FastMCP(
    "SkyTrack UAV MCP",
    instructions=(
        "MCP Server for inspecting SkyTrack 3D Gazebo worlds & live UAV telemetry, "
        "planning and drawing visual routes onto the SkyTrack Electron map UI (plan.json), "
        "executing routes via GCS Backend (:20002) & Path Planner (:20007), and authoring/running "
        "Python UAV autonomy scripts (local_planner SDK) inside the ROS 2 Jazzy container."
    ),
)

_gcs = SkyTrackGCSClient()


# =====================================================================
# 1. MAP & TELEMETRY INSPECTION TOOLS
# =====================================================================


@mcp.tool()
async def list_missions_and_worlds() -> Dict[str, Any]:
    """List all SkyTrack projects and missions in local ClientData along with all available
    3D Gazebo worlds (.sdf) and Path Planner API health status.

    Call this first to discover the active mission_id, current world (e.g. 'warehouse', 'default'),
    vehicle type, and current spawn location.
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
    and script.py Python code). If mission_id is omitted, reads the most recently active mission.
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
    exact 3D bounding boxes (AABB in ENU meters) and generate a 2D top-down ASCII occupancy map
    at the desired flight altitude `slice_altitude_m`.

    Coordinate convention:
    - X = East (meters)
    - Y = North (meters)
    - Z = Up / Altitude (meters)
    - 'S' on the ASCII map marks origin (0, 0), '#' marks obstacles at `slice_altitude_m`, '.' is free space.
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
    all 3D collision geometries in `world_name.sdf` (with an obstacle inflation safety margin of `clearance_m`).

    Returns `is_collision_free: True/False` and details of any intersecting wall/obstacle legs.
    """
    return check_waypoints_collisions(
        world_name=world_name,
        waypoints=waypoints,
        clearance_m=clearance_m,
    )


@mcp.tool()
async def get_uav_telemetry() -> Dict[str, Any]:
    """Fetch real-time UAV telemetry from the MAVLink bridge and GCS action feedback stream.

    Returns:
    - `is_armed`, `landed_state` ('ON_GROUND', 'IN_AIR', etc.), `flight_mode`
    - `battery_percentage`, `heading_deg`, `attitude_deg` (roll, pitch, yaw)
    - `local_enu_m` ({x_east_m, y_north_m, z_up_m}) and `local_ned_m` ({north_m, east_m, down_m})
    - `gps_position` (lat, lng, altitude) and `home_point`
    - `gcs_action_feedback` (status of takeoff, land, rtl, mission_execution)
    """
    mav_data = fetch_live_mavlink_telemetry()
    gcs_fb = await _gcs.get_gcs_feedback_snapshot()
    return {
        "telemetry": mav_data,
        "gcs_action_feedback": gcs_fb,
    }


# =====================================================================
# 2. ROUTE PLANNING & VISUAL MAP DRAWING TOOLS
# =====================================================================


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
    """Generate an optimized zigzag coverage route inside a polygon area (in local ENU meters `[{"x": ..., "y": ...}]`)
    using the SkyTrack Path Planner API (:20007), optionally split around No-Fly Zones, and draw it onto
    the SkyTrack map UI (`plan.json`).

    Args:
        area_coords: List of polygon vertices `[{"x": float, "y": float}, ...]` (minimum 3 vertices).
        spacing_m: Distance between parallel sweep lines in meters.
        orientation_deg: Sweep angle in degrees (default 90.0).
        altitude_m: Flight altitude Z in meters for the generated waypoints.
        hole_coords: Optional list of obstacle polygon holes inside the area.
        no_fly_zones: Optional list of NFZ definitions to split legs around.
        save_to_mission_ui: If True, automatically draws the computed route into `plan.json` of `mission_id`.
        mission_id: Target mission ID (defaults to active mission).
    """
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
    """Draw a visual route directly onto the SkyTrack Map UI (`plan.json` & `mission.json`).

    Each item in `waypoints` can be:
    - `{"x": 4.0, "y": -5.0, "z": 2.5}` (ENU meters: x=East, y=North, z=Up altitude)
    - Optionally include `"after_action": "drop-ball" | "take-photo" | "start-recording-video" | "stop-recording-video"`
      to attach payload or camera actions at that waypoint!

    This sets `codeMode: false` on the mission so the route is visible in the SkyTrack Map view.
    """
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
    """Execute a waypoint route mission on the UAV via the GCS Control API (`POST :20002/mission/v2/execute`).

    If `waypoints` is provided, optionally saves them to `plan.json` (`also_save_to_ui=True`) and dispatches
    them to the drone. If `waypoints` is omitted, loads the saved waypoints from `plan.json` of `mission_id`.
    """
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
    """Send direct flight or mission control commands to the UAV (:20002).

    Supported `command` values:
    - `'takeoff'`: Take off to `altitude_m` (1.0m - 50.0m).
    - `'land'`: Land at current position (`smart=True` uses planner-assisted landing).
    - `'rtl'`: Return to launch point (`smart=True` uses planner-assisted RTL).
    - `'pause_mission'`: Pause active mission execution.
    - `'resume_mission'`: Resume paused mission.
    - `'cancel_mission'`: Cancel current mission execution.
    - `'smart_land'`: Trigger emergency smart landing.
    """
    return await _gcs.control_flight_or_mission(
        command=command,
        altitude_m=altitude_m,
        smart=smart,
    )


# =====================================================================
# 3. PYTHON UAV CODE AUTHORING & EXECUTION TOOLS
# =====================================================================


@mcp.tool()
def get_uav_python_sdk_reference() -> Dict[str, Any]:
    """Return the exact function signatures, coordinate conventions, and verified templates
    for writing SkyTrack UAV Python scripts using the `local_planner` SDK.

    Always consult this before writing custom UAV Python scripts so function arguments match 100%.
    """
    return {
        "sdk_module": "local_planner",
        "execution_container": "skytrack-simulation-skytrack-autonomy-1",
        "important_rules": [
            "1. `scenario(ctx)` MUST be a Python generator function using `yield` for each step.",
            "2. Set `scenario.requires_senses = ['pose', 'obstacle', 'status']` on the scenario function.",
            "3. `takeoff(*, alt_m=2.5)` uses keyword argument `alt_m` (NOT `altitude`).",
            "4. `fly_to(north=..., east=..., alt_m=..., target_speed=...)` uses `north` (Y axis in ENU) and `east` (X axis in ENU), plus `alt_m` (positive meters up).",
            "5. Always wrap execution in `with boot_drone() as drone: drone.fly(scenario); drone.run()`.",
        ],
        "function_signatures": {
            "boot_drone": "boot_drone() -> ContextManager[Drone]",
            "takeoff": "takeoff(*, alt_m: float = 3.0, name: Optional[str] = None) -> SkillStep",
            "fly_to": "fly_to(x=None, y=None, z=None, *, north: Optional[float] = None, east: Optional[float] = None, alt_m: Optional[float] = None, direct: bool = False, target_speed: Optional[float] = None, yaw_mode=None, yaw_rate_deg_s: Optional[float] = None, name: Optional[str] = None) -> SkillStep",
            "fly_to_ned": "fly_to_ned(x: float, y: float, z: float, *, direct: bool = False, target_speed: Optional[float] = None, name: Optional[str] = None) -> SkillStep",
            "orbit": "orbit(center=None, *, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, radius_m: float = 5.0, period_s: float = 20.0, duration_s: float = 60.0, name: str = 'orbit') -> SkillStep",
            "helix": "helix(center=None, *, z_end=None, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, alt_m_end: Optional[float] = None, radius_m: float = 5.0, period_s: float = 20.0, duration_s: float = 60.0, name: str = 'helix') -> SkillStep",
            "yaw_to": "yaw_to(face=None, *, north: Optional[float] = None, east: Optional[float] = None, name: str = 'yaw_to') -> SkillStep",
            "capture": "capture(*, output_dir: str = '~/.ros/captures', filename: Optional[str] = None, timeout_s: float = 5.0, name: str = 'capture') -> SkillStep",
            "brake": "brake(*, name: str = 'brake') -> SkillStep",
            "brake_and_settle": "brake_and_settle(*, name: str = 'brake') -> SkillStep",
            "land": "land(*, name: str = 'land') -> SkillStep",
        },
        "example_script": (
            '"""Autonomous UAV flight script using SkyTrack local_planner SDK."""\n\n'
            "from typing import Any, Iterator\n"
            "from local_planner import (\n"
            "    boot_drone,\n"
            "    takeoff,\n"
            "    fly_to,\n"
            "    orbit,\n"
            "    capture,\n"
            "    brake,\n"
            "    land,\n"
            ")\n\n"
            "def scenario(ctx: Any) -> Iterator[Any]:\n"
            "    yield takeoff(alt_m=2.5)\n"
            "    yield fly_to(north=5.0, east=0.0, alt_m=2.5, target_speed=2.0)\n"
            "    yield capture(filename='waypoint_1.jpg')\n"
            "    yield orbit(center_north=5.0, center_east=2.0, alt_m=2.5, radius_m=2.0, duration_s=15.0)\n"
            "    yield fly_to(north=0.0, east=0.0, alt_m=2.5)\n"
            "    yield brake()\n"
            "    yield land()\n\n"
            'scenario.requires_senses = ["pose", "obstacle", "status"]\n\n'
            "def main() -> None:\n"
            "    with boot_drone() as drone:\n"
            "        drone.fly(scenario)\n"
            "        drone.run()\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
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
    """Convert a visual waypoint route (either passed as `waypoints` or read from `plan.json` of `mission_id`)
    into a runnable SkyTrack `local_planner` Python script (`script.py`).

    Automatically maps ENU `x` -> `east` and ENU `y` -> `north`, and translates camera/payload actions.
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

    steps: List[str] = [f"    yield takeoff(alt_m={takeoff_altitude:.2f})"]
    for idx, wp in enumerate(waypoints, start=1):
        wp_type = wp.get("type", "navigate")
        if wp_type in ("navigate", "navigation", "waypoint") or ("x" in wp and "y" in wp):
            if "data" in wp and isinstance(wp["data"], list) and len(wp["data"]) == 3:
                east_x, north_y, alt_z = (
                    float(wp["data"][0]),
                    float(wp["data"][1]),
                    float(wp["data"][2]),
                )
            else:
                east_x = float(wp.get("x", wp.get("east", 0.0)))
                north_y = float(wp.get("y", wp.get("north", 0.0)))
                alt_z = float(wp.get("z", wp.get("alt_m", takeoff_altitude)))
            steps.append(
                f"    yield fly_to(north={north_y:.3f}, east={east_x:.3f}, "
                f"alt_m={alt_z:.3f}, target_speed={target_speed:.2f}, name='wp_{idx}')"
            )
            if wp.get("after_action") in ("take-photo", "snapshot"):
                steps.append(f"    yield capture(filename='wp_{idx}.jpg')")
        elif wp_type in ("take-photo", "snapshot"):
            steps.append(f"    yield capture(filename='step_{idx}.jpg')")

    steps.append("    yield fly_to(north=0.0, east=0.0, alt_m=" + f"{takeoff_altitude:.2f}, name='return_home')")
    steps.append("    yield brake()")
    steps.append("    yield land()")

    body = "\n".join(steps)
    script_code = f'''"""Auto-generated SkyTrack UAV Python Script from Route Waypoints."""

from typing import Any, Iterator
from local_planner import (
    boot_drone,
    takeoff,
    fly_to,
    capture,
    brake,
    land,
)


def scenario(ctx: Any) -> Iterator[Any]:
{body}


scenario.requires_senses = ["pose", "obstacle", "status"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
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
    """Validate a Python UAV script (AST syntax & `local_planner` keyword verification) and save it
    to `script.py` in the SkyTrack mission folder so it appears in the SkyTrack App Code Editor.
    """
    validation = validate_uav_python_code(python_code)
    if not validation["valid"]:
        return {
            "saved": False,
            "validation": validation,
        }

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
    """Deploy and execute a Python UAV script inside the `skytrack-simulation-skytrack-autonomy-1`
    container with ROS 2 Jazzy and `local_planner` initialized.

    - If `python_code` is passed, it is validated, saved to `script.py` of `mission_id`, copied into
      the autonomy container, and started.
    - If `python_code` is omitted, the existing `script.py` from `mission_id` is executed.
    """
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
    """Stop any currently running Python UAV script (`user-script.py`) inside `skytrack-simulation-skytrack-autonomy-1`."""
    return stop_uav_python_in_container()


@mcp.tool()
def get_uav_script_logs(tail_lines: int = 80) -> Dict[str, Any]:
    """Read stdout/stderr logs and running state of the Python UAV script inside `skytrack-simulation-skytrack-autonomy-1`."""
    return read_uav_python_logs(tail_lines=tail_lines)


# =====================================================================
# 4. CLOUD API, SIMULATION LIFECYCLE & CLOSED-LOOP WORKFLOW TOOLS
# =====================================================================


@mcp.tool()
def list_skytrack_cloud_projects() -> List[Dict[str, Any]]:
    """List all projects for the authenticated user directly from the SkyTrack Cloud API
    (https://platform.getskytrack.com/api/v1/projects).

    Returns project IDs (e.g. '01M11QPK1C3Y5GFNBDADS8H7MC'), names, and mission counts.
    """
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
    """Create a new mission directly on the SkyTrack Cloud Platform AND initialize its
    local runtime cache in `ClientData/prj-.../mis-...`.

    This immediately makes the mission appear inside the SkyTrack Desktop App and Mobile UI!
    """
    cloud_res = create_cloud_mission(
        name=name,
        project_id=project_id,
        world=world,
        actions=actions or [],
    )
    new_mis_id = str(cloud_res.get("id") or "").removeprefix("mis-")

    # Sync local ClientData cache so Electron can open it locally
    draw_res = write_visual_route(
        waypoints=actions or [],
        mission_id=new_mis_id,
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=2.5,
        target_speed=2.0,
        world=world,
        vehicle=vehicle,
    )

    return {
        "cloud_mission": cloud_res,
        "local_cache": draw_res,
    }


@mcp.tool()
def sync_mission_to_cloud(mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Upload local changes from `plan.json` and `mission.json` to the SkyTrack Cloud Platform
    so the web/app UI shows the latest waypoints and actions.
    """
    details = read_mission_details(mission_id=mission_id)
    mis_id = details["mission_id"]
    plan = details.get("plan", {})
    mission_meta = details.get("mission", {})
    sequences = plan.get("sequences", [])
    actions = []
    for seq in sequences:
        actions.extend(seq.get("actions", []))

    cloud_update = update_cloud_mission(
        mission_id=mis_id,
        world=mission_meta.get("world"),
        actions=actions,
        spawn_location=plan.get("spawnLocation"),
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
    """Manage the SkyTrack Docker Simulation Stack.

    Args:
        action: 'status' (check container health), 'start' (boot deamon + simulation containers),
                or 'stop' (shut down simulation).
        world: World name to boot (e.g. 'warehouse', 'default', 'farm-petersburg').
        vehicle: Vehicle model (e.g. 'x500_livox_mid_360', 'x500_tennis_balls_no_cam', 'x500_mono_cam').
        spawn_pose: Optional [x, y, z] spawn position in meters.
    """
    act = action.lower().strip()
    if act == "status":
        return get_simulation_health()
    if act == "start":
        return start_simulation_stack(world=world, vehicle=vehicle, spawn_pose=spawn_pose)
    if act == "stop":
        return stop_simulation_stack()
    raise ValueError(f"Unknown action '{action}'. Valid actions: 'status', 'start', 'stop'.")


@mcp.tool()
async def run_mission_and_wait_completion(
    mission_id: Optional[str] = None,
    waypoints: Optional[List[Dict[str, Any]]] = None,
    poll_interval_s: float = 3.0,
    max_wait_seconds: float = 120.0,
) -> Dict[str, Any]:
    """Closed-loop autonomous flight execution:
    1. Sends the mission to the UAV via GCS API (:20002).
    2. Polls live telemetry every `poll_interval_s` seconds, monitoring position, battery, and flight state.
    3. Detects liftoff (`IN_AIR`), waypoint progress, and safe landing (`ON_GROUND`).
    4. Returns a comprehensive flight summary upon mission completion.
    """
    exec_res = await execute_route_mission(
        waypoints=waypoints,
        mission_id=mission_id,
        also_save_to_ui=True,
    )
    if not exec_res.get("ok"):
        return {
            "status": "failed_to_dispatch",
            "error": exec_res.get("response"),
        }

    import asyncio
    import time

    start_time = time.time()
    telemetry_samples: List[Dict[str, Any]] = []
    airborne_detected = False
    landed_after_airborne = False

    while (time.time() - start_time) < max_wait_seconds:
        await asyncio.sleep(poll_interval_s)
        tel_data = fetch_live_mavlink_telemetry()
        landed_state = tel_data.get("landed_state")

        sample = {
            "elapsed_s": round(time.time() - start_time, 1),
            "landed_state": landed_state,
            "flight_mode": tel_data.get("flight_mode"),
            "battery": tel_data.get("battery_percentage"),
            "enu": tel_data.get("local_enu_m"),
            "armed": tel_data.get("is_armed"),
        }
        telemetry_samples.append(sample)

        if landed_state in ("IN_AIR", "TAKEOFF", "LANDING"):
            airborne_detected = True

        if airborne_detected and landed_state == "ON_GROUND":
            landed_after_airborne = True
            break

    total_duration = round(time.time() - start_time, 1)
    return {
        "status": "completed_safely" if landed_after_airborne else "finished_or_timeout",
        "airborne_detected": airborne_detected,
        "landed_safely": landed_after_airborne,
        "total_duration_s": total_duration,
        "sample_count": len(telemetry_samples),
        "final_telemetry": telemetry_samples[-1] if telemetry_samples else None,
        "telemetry_samples": telemetry_samples,
    }


@mcp.tool()
def harvest_flight_report(
    mission_id: Optional[str] = None,
    save_to_disk: bool = True,
) -> Dict[str, Any]:
    """Harvest flight execution events, telemetry history, and container logs, and compile
    an official Flight Report (`flight_report.json` and `flight_report.md`) inside the mission folder.
    """
    import datetime

    details = read_mission_details(mission_id=mission_id)
    mis_dir = Path(details["path"])
    mis_id = details["mission_id"]
    prj_id = details["project_id"]

    logs = read_uav_python_logs(tail_lines=100)
    telem = fetch_live_mavlink_telemetry()

    plan = details.get("plan", {})
    mission_meta = details.get("mission", {})
    sequences = plan.get("sequences", [])
    actions = []
    for seq in sequences:
        actions.extend(seq.get("actions", []))

    report_data = {
        "project_id": prj_id,
        "mission_id": mis_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "world": mission_meta.get("world", "default"),
        "vehicle": mission_meta.get("vehicle", "x500_livox_mid_360"),
        "total_actions": len(actions),
        "final_telemetry": telem,
        "autonomy_logs_summary": logs.get("logs", "")[-500:],
    }

    md_report = f"""# SkyTrack Autonomous Flight Report

- **Mission ID:** `{mis_id}`
- **Project ID:** `{prj_id}`
- **Date/Time:** {report_data['timestamp']}
- **Simulation World:** `{report_data['world']}`
- **Vehicle Model:** `{report_data['vehicle']}`
- **Planned Waypoints / Actions:** {len(actions)}

## 1. Flight Telemetry Status
- **Connection:** {'Connected' if telem.get('connected') else 'Disconnected'}
- **Landed State:** `{telem.get('landed_state')}`
- **Battery Remaining:** `{telem.get('battery_percentage')}%`
- **Flight Mode:** `{telem.get('flight_mode')}`
- **Final Local ENU Position:** `{telem.get('local_enu_m')}`

## 2. Autonomy Container Execution Log
```text
{logs.get('logs', 'No logs recorded.')}
```
"""

    if save_to_disk:
        json_file = mis_dir / "flight_report.json"
        md_file = mis_dir / "flight_report.md"
        json_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        md_file.write_text(md_report, encoding="utf-8")

    return {
        "report": report_data,
        "markdown_report": md_report,
        "saved_to_folder": str(mis_dir) if save_to_disk else None,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
