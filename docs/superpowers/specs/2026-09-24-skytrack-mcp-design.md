# SkyTrack MCP Server (`skytrack-mcp`) — Architecture & Design Specification

**Date:** 2026-09-24  
**Author:** Claude Code & Phuc Dang  
**Status:** Approved for Implementation

---

## 1. Overview & Goals

`skytrack-mcp` is a Model Context Protocol (MCP) server built with Python (`FastMCP`) that empowers AI models (Claude, Gemini, Cursor, Claude Code) to:
1. **Inspect Map & Live UAV Telemetry:** Parse 3D Gazebo `.sdf` world geometries (models, walls, racks, bounding boxes, spherical coordinates), generate 2D top-down obstacle occupancy grids at target flight altitudes, verify route collision-freedom, and read real-time UAV telemetry from `mavlink-bridge` and `gcs-backend`.
2. **Plan & Draw Routes on SkyTrack UI:** Compute optimal coverage paths and NFZ-split routes via the SkyTrack Path Planner API (`127.0.0.1:20007`), write visual routes directly into SkyTrack's `plan.json` and `mission.json` inside `~/Library/Application Support/SkyTrack/ClientData`, and trigger execution via `UAV Control API` (`127.0.0.1:20002`).
3. **Author, Validate & Execute Python UAV Scripts:** Generate and AST-validate Python scripts using the `local_planner` / `skytrack_autonomy` SDK (`boot_drone`, `takeoff`, `fly_to`, `fly_to_ned`, `orbit`, `helix`, `yaw_to`, `capture`, `brake`, `land`), sync them to `script.py` in SkyTrack's `ClientData`, and execute/stop/monitor them inside the `skytrack-simulation-skytrack-autonomy-1` ROS 2 Jazzy container.

---

## 2. System Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│              AI Agent (Claude Code / Claude Desktop)              │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │ MCP Protocol (stdio / SSE)
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│                   SkyTrack MCP Server (FastMCP)                   │
│                                                                   │
│  ┌────────────────────┐ ┌───────────────────┐ ┌────────────────┐  │
│  │  Map & SDF Engine  │ │ Route & UI Sync   │ │ Python Runner  │  │
│  │ - SDF XML Parser   │ │ - :20007 Planner  │ │ - AST Linter   │  │
│  │ - 3D AABB Collide  │ │ - plan.json Writer│ │ - script.py UI │  │
│  │ - 2D ASCII Grid    │ │ - :20002 Executor │ │ - Docker ROS 2 │  │
│  └─────────┬──────────┘ └─────────┬─────────┘ └────────┬───────┘  │
└────────────┼──────────────────────┼────────────────────┼──────────┘
             │                      │                    │
             ▼                      ▼                    ▼
┌────────────────────────┐ ┌─────────────────┐ ┌────────────────────┐
│ Gazebo & MAVLink Bridge│ │ SkyTrack App UI │ │ skytrack-autonomy  │
│ - /var/www/.../*.sdf   │ │ ClientData/     │ │ ROS 2 Jazzy +      │
│ - ws://127.0.0.1:9005  │ │ prj-*/mis-*     │ │ local_planner SDK  │
└────────────────────────┘ └─────────────────┘ └────────────────────┘
```

---

## 3. MCP Tool Catalog

### 3.1 Map & Telemetry Inspection (`map_tools.py`)
1. `list_missions_and_worlds()` — Lists all local SkyTrack projects (`prj-*`), missions (`mis-*`) with their metadata (`world`, `vehicle`, `codeMode`, `spawnLocation`, `waypoints_count`), and all 28 Gazebo `.sdf` worlds.
2. `inspect_world_map(world_name, slice_altitude_m=2.5, grid_bounds=20.0)` — Parses `/var/www/files/px4-gz/worlds/{world_name}.sdf`, extracts 3D collision bounding boxes (`AABB`) and included models, and renders a 2D ASCII top-down obstacle slice at `slice_altitude_m`.
3. `check_route_collisions(world_name, waypoints, clearance_m=0.4)` — Tests 3D line segments between consecutive ENU `[x, y, z]` waypoints against all world collision boxes and reports any obstacle intersections.
4. `get_uav_telemetry()` — Fetches real-time MAVLink telemetry (`position`, `home_point`, local `enu_m` / `ned_m`, `battery_percentage`, `flight_mode`, `is_armed`, `landed_state`, `heading`, `attitude`) and GCS feedback (`/ws/feedback`).
5. `set_simulation_world_and_avoidance(world_name=None, avoidance_mode=None)` — Configures active world name and obstacle avoidance mode (`avoid` / `brake`) via GCS Backend (`:20002`).

### 3.2 Route Planning & Map Drawing (`route_tools.py`)
6. `plan_coverage_route(area_coords, spacing_m=2.0, orientation_deg=90.0, altitude_m=2.5, hole_coords=None, no_fly_zones=None)` — Calls `POST :20007/plan-coverage-xy` and optionally `POST :20007/split-waypoints-nfz` to compute an optimized zigzag coverage route in local ENU meters.
7. `draw_route_on_map(waypoints, mission_id=None, spawn_location=None, takeoff_altitude=2.0, target_speed=2.0, safety_option="avoid", end_action="rtl")` — Writes the route and waypoint actions (`navigate`, `drop-ball`, `start-recording-video`, `stop-recording-video`, `take-photo`) directly into `plan.json` and updates `mission.json` (`codeMode=False`).
8. `execute_route_mission(waypoints=None, mission_id=None, takeoff_altitude=2.0, target_speed=2.0, avoidance_mode="avoid", no_fly_zones=None, end_action="rtl")` — Dispatches a validated `FrontendMissionExecutionRequest` to `POST :20002/mission/v2/execute`.
9. `control_mission_and_flight(command, altitude_m=2.5)` — Controls active missions and direct flight (`takeoff`, `land`, `rtl`, `pause_mission`, `resume_mission`, `cancel_mission`, `smart_land`).

### 3.3 Python UAV Code Authoring & Execution (`code_tools.py`)
10. `get_uav_python_sdk_reference(template_type="all")` — Returns complete documentation and runnable templates for the `local_planner` Python SDK (`boot_drone`, `takeoff`, `fly_to`, `fly_to_ned`, `orbit`, `helix`, `yaw_to`, `capture`, `brake`, `land`, `ControlMode`, `Command`).
11. `write_and_save_uav_script(python_code, mission_id=None)` — Performs static AST syntax and structure checks on `python_code`, saves it to `script.py` in the target mission directory, and flips `codeMode: true` in `mission.json`.
12. `execute_uav_python_script(python_code=None, mission_id=None, background=True, wait_seconds=4.0)` — Copies the Python script into `skytrack-simulation-skytrack-autonomy-1`, launches it inside the ROS 2 Jazzy environment (`source /opt/ros/jazzy/setup.bash && source /app/setup.sh`), and captures execution status and logs.
13. `stop_uav_python_script()` — Gracefully sends `SIGINT` / terminates any running user Python script in `skytrack-simulation-skytrack-autonomy-1`.
14. `get_uav_script_logs(tail_lines=80)` — Reads stdout/stderr output from the latest or currently running Python script inside the autonomy container.
