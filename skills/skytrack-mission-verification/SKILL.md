---
name: skytrack-mission-verification
description: Compiles requirement-by-requirement verification matrices (PASS / FAIL / UNKNOWN) to confirm mission success against evidence.
---

# SkyTrack Mission Verification Skill

## Purpose
Enforces the core engineering principle: **Never assume success because the simulator started or the path looks plausible**. Cross-examines actual harvested flight evidence against every initial task requirement to produce a deterministic verification matrix with concrete proof.

## Trigger Conditions
- Triggered after `skytrack-report-analysis` to evaluate whether the mission achieved its objectives.
- Triggered before declaring an assignment complete.

## Relevant MCP Tools
- `tool_skytrack_verify_mission_requirements(requirements, mission_id)`
- `tool_skytrack_report_read(mission_id)`
- `tool_skytrack_validate_mission(mission_id)`

## Verification Rules & Standards
1. **Three-State Verdicts:** Every requirement item must evaluate to `PASS`, `FAIL`, or `UNKNOWN`.
2. **Never promote UNKNOWN to PASS:** If telemetry or logs are missing, the status is `UNKNOWN`, which is treated as non-passing.
3. **Mandatory Pass Condition:** Overall mission verdict is `PASS` ONLY when 100% of mandatory requirements have verified `PASS` status.
4. **Concrete Evidence Clause:** Every item must record the specific field or log line proving the status (e.g. `telemetry.landed_state == 'ON_GROUND'`, `media.captures_count == 3`).

## Standard Verification Checklist Items
- `landed_safely`: Drone completed flight and returned to `ON_GROUND`.
- `min_waypoints`: All planned inspection waypoints were visited.
- `payload_drops`: Number of drop events matches requirement.
- `captures`: Required snapshot images were saved to disk.
- `battery_margin`: Flight completed with battery remaining above critical threshold (> 15%).
- `collision_free`: Zero obstacle intersections recorded during planning and flight.
