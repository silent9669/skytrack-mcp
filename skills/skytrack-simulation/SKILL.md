---
name: skytrack-simulation
description: Manages the 7-container Docker simulation stack, mission dispatching, and real-time flight telemetry observation loops.
---

# SkyTrack Simulation Skill

## Purpose
Governs the execution phase of SkyTrack missions: ensuring container health across the 7 microservices (`gazebo`, `px4`, `mission-computer`, `skytrack-autonomy`, `gcs-backend`, `mavlink-bridge`, `websocket-proxy`), dispatching routes or launching Python scripts, and running real-time polling observation loops until touchdown.

## Trigger Conditions
- Triggered when starting, restarting, or monitoring a simulation run.
- Triggered when live telemetry streams need to be sampled.

## Relevant MCP Tools
- `tool_skytrack_simulation_start`, `tool_skytrack_simulation_stop`, `tool_skytrack_simulation_restart`
- `tool_skytrack_docker_status`: Health check across all 7 containers.
- `execute_route_mission`: Dispatch via GCS Control API (`:20002/mission/v2/execute`).
- `execute_uav_python_script`: Run Python script in ROS 2 container (`skytrack-autonomy`).
- `run_mission_and_wait_completion`: Automated closed-loop execution and polling until landed.
- `control_uav_flight`: Emergency interventions (`takeoff`, `land`, `rtl`, `pause`, `smart_land`).

## Execution Procedure
1. **Pre-flight Healthcheck:** Query `tool_skytrack_docker_status()`. If any core container is down, call `tool_skytrack_simulation_start()`.
2. **Dispatch Mission:**
   - For Visual Route: Call `execute_route_mission(mission_id=...)`.
   - For Python Script: Call `execute_uav_python_script(mission_id=...)`.
3. **Continuous Polling Loop:**
   - Sample telemetry every 3-5 seconds.
   - Detect state transitions: `ON_GROUND` -> `TAKEOFF` -> `IN_AIR` -> `LANDING` -> `ON_GROUND`.
   - Monitor battery percentage (trigger `rtl` if battery drops below 15%).
   - Log waypoint progress and coordinate history.
4. **Touchdown Verification:** Confirm `landed_state == 'ON_GROUND'` and `armed == False` before initiating report harvesting.
