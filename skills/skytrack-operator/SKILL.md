---
name: skytrack-operator
description: Master orchestration skill for operating SkyTrack Mission Studio through the autonomous closed-loop lifecycle.
---

# SkyTrack Operator Skill

## Purpose
Orchestrates the entire autonomous flight lifecycle: understanding natural language assignments, inspecting simulated 3D environments, authoring collision-free routes or Python scripts, managing the Docker simulation stack, observing live flight execution, and verifying evidence-backed mission reports.

## Trigger Conditions
- Trigger when the user requests an autonomous drone mission in SkyTrack (e.g. "fly through coordinates", "inspect warehouse", "scan agricultural field", "drop payload on targets").
- Trigger when executing end-to-end evaluation missions.

## Prerequisites
- SkyTrack application installed at `/Applications/SkyTrack.app`.
- Docker Desktop running with the `skytrack-simulation` and `skytrack-deamon` image stacks available.
- `skytrack-mcp` server connected and active.

## Relevant MCP Tools
- `tool_skytrack_get_context`, `tool_skytrack_status`, `tool_skytrack_healthcheck`
- `tool_skytrack_list_projects`, `tool_skytrack_create_mission`, `tool_skytrack_open_mission`
- `tool_skytrack_inspect_world`, `check_route_collisions`
- `plan_coverage_route`, `draw_route_on_map`, `tool_skytrack_patch_mission`, `tool_skytrack_validate_mission`
- `tool_skytrack_simulation_start`, `tool_skytrack_simulation_observe`, `run_mission_and_wait_completion`
- `tool_skytrack_report_read`, `tool_skytrack_verify_mission_requirements`, `harvest_flight_report`

## Normal Workflow
1. **Understand Task:** Invoke `skills/skytrack-task-understanding` to generate the formal `MissionRequirements` specification.
2. **Context Inspection:** Query `tool_skytrack_get_context` to identify current project, mission, world, and vehicle.
3. **World Inspection:** Invoke `skills/skytrack-world-inspection` to inspect 3D obstacles and 2D occupancy grid slice.
4. **Route Planning:** Invoke `skills/skytrack-route-planning` to compute collision-free waypoints with required margins.
5. **Mission Authoring:** Invoke `skills/skytrack-mission-authoring` to write `plan.json` / `script.py` and run static pre-flight validation.
6. **Simulation Execution:** Invoke `skills/skytrack-simulation` to boot containers, launch the drone, and monitor telemetry until touchdown.
7. **Report Analysis & Verification:** Invoke `skills/skytrack-report-analysis` and `skills/skytrack-mission-verification` to compile evidence.
8. **Repair Loop:** If any mandatory requirement fails, diagnose root cause and repeat from Step 4.

## Decision Rules
- **Rule 1 (Safety First):** Never launch a mission that fails static validation or has unverified 3D collision intersections.
- **Rule 2 (Evidence-Backed):** Never declare mission success based merely on simulation startup; verify actual touchdown and report metrics.
- **Rule 3 (Minimal Intervention):** Prefer high-level structured JSON/API tools over raw mouse coordinates.

## Evidence Requirements
- Static validation result (`valid: true`).
- 3D collision check result (`is_collision_free: true`).
- Telemetry trace confirming `IN_AIR` transition followed by `ON_GROUND`.
- Harvested `flight_report.json` and verification matrix with 100% mandatory PASS.

## Failure Modes & Recovery
- Simulator not responding: Call `tool_skytrack_recover(issue_type='auto')`.
- Collision detected during planning: Replan waypoints with increased clearance or intermediate corridor waypoints.
- Drone fails to take off: Verify battery status and confirm world origin spherical coordinates match.

## Stop Conditions
- All mandatory requirements marked `PASS` in verification matrix with concrete evidence.
- Max repair iterations (3) reached without convergence (escalates to operator with diagnostic report).
