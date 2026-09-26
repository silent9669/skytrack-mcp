# SkyTrack MCP Server (`skytrack-mcp`)

Model Context Protocol (MCP) server for the **SkyTrack UAV Simulation & Mission Studio**.

## Features
1. **Map & 3D World Inspection (`inspect_world_map`, `check_route_collisions`, `list_missions_and_worlds`)**
   - Parses Gazebo `.sdf` 3D worlds (`warehouse`, `default`, `city`, `desert-cliff-terrains`, etc.)
   - Computes 3D obstacle Axis-Aligned Bounding Boxes (AABBs)
   - Generates a 2D ASCII top-down occupancy grid map at any flight altitude
   - Verifies whether 3D multi-waypoint routes intersect any walls or shelves
2. **Real-Time UAV Telemetry (`get_uav_telemetry`)**
   - Reads live MAVLink state (`is_armed`, `landed_state`, `flight_mode`, `battery_percentage`, `heading_deg`, `attitude_deg`, GPS, and local ENU/NED coordinates) plus GCS action feedback (`/ws/feedback`).
3. **Visual Route Planning & SkyTrack UI Sync (`plan_coverage_route`, `draw_route_on_map`, `execute_route_mission`)**
   - Computes zigzag coverage strips and No-Fly Zone (NFZ) splits via SkyTrack Path Planner API (`:20007`)
   - Writes visual routes directly into SkyTrack's `plan.json` & `mission.json` inside `~/Library/Application Support/SkyTrack/ClientData`
   - Dispatches missions to the UAV via `POST :20002/mission/v2/execute`
4. **Python UAV Code Authoring & ROS 2 Execution (`get_uav_python_sdk_reference`, `convert_route_to_python_script`, `write_and_save_uav_script`, `execute_uav_python_script`, `stop_uav_python_script`, `get_uav_script_logs`)**
   - Static AST validation for `local_planner` SDK scripts (`boot_drone`, `takeoff`, `fly_to`, `orbit`, `helix`, `capture`, `brake`, `land`)
   - Saves to `script.py` and runs inside `skytrack-simulation-skytrack-autonomy-1` with ROS 2 Jazzy.

## Quick Setup (Claude Code / Claude Desktop / Cursor)

```bash
claude mcp add skytrack -- /Users/phucdang/Documents/skytrack-mcp/.venv/bin/skytrack-mcp
```

Or add to `claude_desktop_config.json` / `.mcp.json`:
```json
{
  "mcpServers": {
    "skytrack": {
      "command": "/Users/phucdang/Documents/skytrack-mcp/.venv/bin/skytrack-mcp"
    }
  }
}
```
# skytrack-mcp
