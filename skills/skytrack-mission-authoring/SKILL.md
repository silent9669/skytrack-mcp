---
name: skytrack-mission-authoring
description: Authors, modifies, and validates SkyTrack missions in both visual route format (plan.json) and ROS 2 Python scripts (script.py).
---

# SkyTrack Mission Authoring Skill

## Purpose
Constructs and modifies SkyTrack mission representations across both supported authoring paradigms:
1. **Visual Route Mode (`plan.json` + `mission.json`):** Renders interactive 3D waypoints and action markers on the SkyTrack Electron Map UI.
2. **Code Mode (`script.py`):** Compiles and validates Python scripts using the `local_planner` SDK (`boot_drone`, `takeoff`, `fly_to`, `capture`, `brake`, `land`) for autonomous container execution.

## Trigger Conditions
- Triggered after route planning to commit waypoints to disk or container.
- Triggered when repairing mission parameters or switching between visual and code modes.

## Relevant MCP Tools
- `tool_skytrack_set_mission`, `draw_route_on_map`, `tool_skytrack_patch_mission`
- `tool_skytrack_validate_mission`
- `write_and_save_uav_script`, `convert_route_to_python_script`, `get_uav_python_sdk_reference`

## Authoring Rules
1. **Visual Route (`plan.json`):**
   - Each waypoint is an action: `{"type": "navigate", "data": [x, y, z]}` in local ENU meters.
   - Attached payload actions follow immediately: `{"type": "drop-ball"}` or `{"type": "take-snapshot"}`.
   - `codeMode` in `mission.json` must be `false` to render on the Map view.
2. **Python Autonomy Script (`script.py`):**
   - Generator function: `def scenario(ctx: Any) -> Iterator[Any]: ... yield takeoff(alt_m=...) ...`
   - Required senses declaration: `scenario.requires_senses = ["pose", "obstacle", "status"]`
   - Production runner: `with boot_drone() as drone: drone.fly(scenario); drone.run()`
   - Always validate with AST static analyzer before saving.

## Post-Authoring Read-Back Gate
- **MANDATORY:** Always read the mission back (`tool_skytrack_get_mission`) after authoring to verify that all actions and waypoints match the intended specification before flight.
