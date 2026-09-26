# SkyTrack Troubleshooting & Self-Healing Guide

## 1. Common Issues & Self-Healing Actions

| Issue | Root Cause | Automated Resolution |
|---|---|---|
| **App shows "0 missions"** | Mission was created on disk cache without cloud registration. | Call `tool_skytrack_create_mission()` or `create_cloud_mission()` to sync to Cloud BFF API. |
| **GCS API :20002 connection refused** | `skytrack-deamon-gcs-backend-1` container is stopped. | Run `tool_skytrack_simulation_start()` or `tool_skytrack_recover()`. |
| **PX4 SITL hangs waiting for Gazebo** | GZ transport cross-container discovery dropped. | Set `GZ_RELAY=172.254.0.12` in `px4` service in `docker-compose.yml`. |
| **User script cannot start** | Previous Python script still running in autonomy container. | Call `stop_uav_python_script()` to send SIGINT/SIGTERM. |
| **Waypoint collision detected** | Flight leg intersects obstacle AABB in Gazebo world. | Inspect collision details from `check_route_collisions()`, raise altitude or add corridor waypoint. |
| **SkyTrack window unclickable** | Modal dialog open or window lost focus. | Call `tool_skytrack_focus()` followed by `tool_ui_key("escape")`. |

## 2. Diagnostics Commands
```bash
# Check SkyTrack health via MCP
uv run python -c "from skytrack_mcp.diagnostics.healthcheck import run_full_system_healthcheck; import asyncio; print(asyncio.run(run_full_system_healthcheck()))"

# Check Docker containers
docker ps -a --filter "name=skytrack"

# View MCP server log
tail -f ~/.skytrack-mcp/logs/skytrack_mcp.log
```
