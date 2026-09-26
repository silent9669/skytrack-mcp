# SkyTrack MCP Tools Reference

## 1. Capability Groups & Functions

### Group 1: Environment & Application
- `tool_skytrack_status()`: Checks whether SkyTrack.app is running, retrieves window bounds, and reports Docker container status.
- `tool_skytrack_launch()`: Launches SkyTrack macOS application if inactive.
- `tool_skytrack_focus()`: Brings SkyTrack window to the foreground.
- `tool_skytrack_get_version()`: Returns product version (`1.2.2`), Electron version (`39.8.10`), and adapter version.
- `tool_skytrack_get_context()`: Complete environment snapshot (active project, mission, world, vehicle, simulation readiness).
- `tool_skytrack_healthcheck()`: Comprehensive multi-service diagnostic check.

### Group 2: Projects & Missions
- `tool_skytrack_list_projects()`: Fetches all projects for the authenticated user via Cloud BFF API (`platform.getskytrack.com`).
- `tool_skytrack_list_missions(project_id)`: Lists all local/cached missions.
- `tool_skytrack_open_mission(mission_id)`: Loads full mission metadata, plan, and script.
- `tool_skytrack_create_mission(...)`: Creates mission on Cloud Platform and initializes local ClientData cache.
- `tool_skytrack_clone_mission(...)`: Duplicates an existing mission safely.
- `tool_skytrack_export_mission(mission_id)`: Exports full JSON representation.
- `tool_skytrack_import_mission(...)`: Imports raw mission JSON payload.

### Group 3: Mission Structured Access
- `tool_skytrack_get_mission(mission_id)`: Returns strongly-typed `CanonicalMission` object.
- `tool_skytrack_get_mission_json(mission_id)`: Raw JSON dictionaries of `plan.json` and `mission.json`.
- `tool_skytrack_validate_mission(mission_id)`: Static pre-flight rules checking altitudes, speeds, capacity, and sensors.
- `tool_skytrack_patch_mission(patches, mission_id)`: Transactional patch-style modification with snapshot backup.
- `tool_skytrack_set_mission(waypoints, ...)`: Replaces entire waypoint sequence and metadata.
- `tool_skytrack_save_mission(mission_id)`: Creates a persistent snapshot checkpoint.

### Group 4: World & Environment
- `tool_skytrack_list_worlds()`: Lists all 28 Gazebo simulation worlds.
- `tool_skytrack_select_world(world_name)`: Changes target world for mission.
- `tool_skytrack_get_world_context(world_name)`: Returns spherical coordinates and obstacle counts.
- `tool_skytrack_inspect_world(world_name, slice_altitude_m)`: Extracts 3D obstacle bounding boxes and renders 2D ASCII occupancy map.
- `tool_skytrack_capture_world(file_path)`: Captures screenshot of 3D world view.

### Group 5: Vehicle
- `tool_skytrack_list_vehicles()`: Lists all 11 supported drone models with payload and sensor specs.
- `tool_skytrack_select_vehicle(vehicle_model)`: Selects drone model for active mission.
- `tool_skytrack_get_vehicle_context(vehicle_model)`: Specifications and limits of target drone.

### Group 6: UI & Computer Use
- `tool_ui_snapshot(file_path)`: High-resolution window screenshot.
- `tool_ui_click(rel_x, rel_y)`: Normalized coordinate click within window.
- `tool_ui_type(text)`: Types text into focused element.
- `tool_ui_key(key_name)`: Sends special keys (`escape`, `return`, `tab`).
- `tool_ui_get_state()`: Reports window bounds and visibility.

### Group 7: Simulation Lifecycle & Control
- `tool_skytrack_simulation_start(world, vehicle, spawn_pose)`: Boots 7 Docker containers.
- `tool_skytrack_simulation_stop()`: Shuts down simulation containers.
- `tool_skytrack_simulation_restart(world)`: Clean restart of simulation stack.
- `tool_skytrack_simulation_state()`: Reads live MAVLink telemetry and armed status.
- `tool_skytrack_simulation_observe(max_duration_s)`: Polling loop tracking flight until touchdown.

### Group 8: Reports & Verification
- `tool_skytrack_report_read(mission_id)`: Parses flight logs and outputs Markdown report.
- `tool_skytrack_report_export(mission_id, output_dir)`: Writes `flight_report.json` and `.md`.
- `tool_skytrack_verify_mission_requirements(requirements)`: Evaluates verification matrix (PASS/FAIL/UNKNOWN).

### Group 9: Diagnostics & Recovery
- `tool_skytrack_logs(tail_lines)`: Reads ROS 2 execution logs from container.
- `tool_skytrack_docker_status()`: Health state across all 7 containers.
- `tool_skytrack_diagnostics()`: Runs full system diagnostics.
- `tool_skytrack_recover(issue_type)`: Automated self-healing routines.
