---
name: skytrack-mission-authoring
description: Authors, modifies, and validates SkyTrack missions in both visual route format (plan.json) and ROS 2 Python scripts (script.py) matching GetSkyTrack/skytrack-autonomy-example.
---

# SkyTrack Mission Authoring Skill

## Purpose
Constructs and modifies SkyTrack mission representations across both supported authoring paradigms:
1. **Visual Route Mode (`plan.json` + `mission.json`):** Renders interactive 3D waypoints and action markers on the SkyTrack Electron Map UI.
2. **Code Mode (`script.py`):** Compiles and validates Python scripts using the `local_planner` SDK (`boot_drone`, `takeoff`, `fly_to`, `orbit`, `helix`, `yaw_to`, `capture`, `brake`, `land`, `CameraSense`, `VideoRecorder`) for autonomous container execution.

## Trigger Conditions
- Triggered after route planning to commit waypoints to disk or container.
- Triggered when repairing mission parameters or switching between visual and code modes.

## Relevant MCP Tools
- `tool_skytrack_set_mission`, `draw_route_on_map`, `tool_skytrack_patch_mission`
- `tool_skytrack_validate_mission`
- `write_and_save_uav_script`, `convert_route_to_python_script`, `get_uav_python_sdk_reference`

## Authoring Rules (`GetSkyTrack/skytrack-autonomy-example` Checklist)
1. **Visual Route (`plan.json`):**
   - Each waypoint is an action: `{"type": "navigate", "data": [x, y, z]}` in local ENU meters.
   - Attached payload actions follow immediately: `{"type": "drop-ball"}`, `{"type": "start-recording-video"}`, `{"type": "stop-recording-video"}`, or `{"type": "take-snapshot"}`.
   - `codeMode` in `mission.json` must be `false` to render on the Map view.
2. **Python Autonomy Script (`script.py`) Checklist:**
   - **File Header:** Always start with `from __future__ import annotations` and define `UPPER_CASE` mission constants (`ALTITUDE_M`, `SPEED_MPS`, `OUTPUT_DIR`).
   - **Generator Function:** `def scenario(ctx: Any) -> Iterator[Any]: ... yield takeoff(alt_m=...) ...`
   - **Flight Modes:** Use `fly_to(north=..., east=..., alt_m=..., mode='transit' | 'coverage' | 'direct', replan_mode='fast' | 'slow')`.
   - **Brake Before Capture & Landing:** Always `yield brake()` immediately before `yield capture(...)` and before `yield land()`.
   - **Video Recording Service (`CameraSense` + `VideoRecorder`):**
     * Include `"camera"` in `scenario.requires_senses = ["pose", "obstacle", "status", "camera"]`.
     * Inside `scenario(ctx)`: `rec = ctx.services.recorder`, call `rec.start(clip="mission_recording")` before the target event and `rec.stop()` after.
     * Inside `with boot_drone() as drone:`: call `drone.add_sense(CameraSense())` and `drone.add_service(VideoRecorder(output_dir="~/.ros/recordings", fps=10.0))`.
   - **Battery Units Rule:** `ctx.senses.battery.percent` is on a `0–100` scale (`20.0` = 20%, NOT `0.20`).
   - Always validate with the AST static analyzer before saving.

## Post-Authoring Read-Back Gate
- **MANDATORY:** Always read the mission back (`tool_skytrack_get_mission`) after authoring to verify that all actions and waypoints match the intended specification before flight.
