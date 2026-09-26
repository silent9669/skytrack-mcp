---
name: skytrack-task-understanding
description: Decomposes natural language assignments into formal structured MissionRequirements before planning or execution.
---

# SkyTrack Task Understanding Skill

## Purpose
Translates unconstrained user mission requests into a strongly-typed `MissionRequirements` model covering objectives, target area, mandatory waypoints, altitude ceilings, speed limits, vehicle model, payload actions, obstacle rules, and verifiable success criteria.

## Trigger Conditions
- Triggered at the beginning of any new mission assignment or when requirements change mid-flight.

## Relevant MCP Tools
- `tool_skytrack_list_vehicles`: Check available drone models and payload capacities.
- `tool_skytrack_list_worlds`: Check available Gazebo simulation worlds.
- `tool_skytrack_get_context`: Check current SkyTrack environment state.

## Output Schema
Produces a structured specification:
```json
{
  "mission_title": "String",
  "world": "String",
  "vehicle": "String",
  "area_bounds": { "min_x": float, "max_x": float, "min_y": float, "max_y": float },
  "target_altitude_m": float,
  "max_speed_m_s": float,
  "mandatory_locations": [{ "x": float, "y": float, "z": float, "action": "String" }],
  "coverage_required": bool,
  "payload_actions": [{ "type": "drop-ball" | "take-snapshot" | "spray", "count": int }],
  "end_behavior": "rtl" | "land",
  "safety_clearance_m": float,
  "acceptance_criteria": [{ "name": "String", "type": "String", "expected": "Any", "mandatory": true }]
}
```

## Decision Rules
- If no world is specified, default to the active world from `tool_skytrack_get_context`.
- If firefighting balls are required, vehicle must be `x500_tennis_balls` or `x500_tennis_balls_no_cam`.
- If camera inspection/snapshots are required, vehicle must have camera tag (`x500_mono_cam`, `x500_gimbal`, `x500_tennis_balls`).
- If LiDAR point clouds are required, vehicle must be `x500_livox_mid_360`.
- All altitudes must default to safe clearance (typically 2.0m - 5.0m depending on obstacle heights).

## SkyTrack Autonomy Level Mapping Table (`GetSkyTrack/skytrack-autonomy-example`)
Choose the right execution paradigm and autonomy level for the user's request:
| Level | Complexity & Use Case | Key SDK Primitives (`get_autonomy_level_template(level)`) |
|---|---|---|
| **Level 1 (Basics)** | Point-to-point or simple polygon waypoints (`hello_mission`, `waypoints_mission`). | `takeoff`, `fly_to(north, east, alt_m)`, `brake`, `land` |
| **Level 2 (Patterns)** | Circular inspection, spiral climb, heading lock, or lawnmower area scan (`orbit`, `helix`, `lawnmower`). | `orbit`, `helix`, `yaw_to`, `fly_to(mode="coverage", replan_mode="fast", yaw_mode="course")` |
| **Level 3 (Logic)** | Multi-sector patrols with conditional branching or battery return-to-home (`sub_missions`, `battery_aware`). | `yield from sub_mission(...)`, `ctx.senses.battery.percent` (`0–100` scale) |
| **Level 4 (Payload/AI)** | Video recording, still photography, crop spraying, or ONNX object detection (`record_video`, `sprayer`, `detect_objects`). | `CameraSense`, `VideoRecorder`, `Snapshot`, `Sprayer`, `Detector` |
| **Level 5 (Extensions)** | Custom geofence monitors, non-blocking timed hovers, CSV telemetry loggers, or custom `ControlMode` + `Command`. | `Sense` (`attach`+`update`), `Skill` (`ScheduleGroup.CONTROL`), `Service` (`ScheduleGroup.MEDIA`) |
| **Level 6 (Full-Stack)** | Complete industrial/agricultural site survey combining grid coverage, video, custom sense/skill/service, and battery guard. | `site_survey_mission` (all of Levels 1–5 combined) |

