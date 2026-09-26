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
