"""MCP Prompt templates for standard autonomous SkyTrack workflows."""

from __future__ import annotations

from typing import Any, Dict, List


def get_prompt_templates() -> Dict[str, Dict[str, Any]]:
    return {
        "skytrack-solve-mission": {
            "name": "skytrack-solve-mission",
            "description": "Orchestrates the full Observe -> Plan -> Execute -> Verify autonomous mission workflow.",
            "arguments": [
                {
                    "name": "assignment",
                    "description": "Natural language mission assignment (e.g. inspect warehouse aisles, drop balls on racks, scan crops).",
                    "required": True,
                },
                {
                    "name": "world",
                    "description": "Gazebo simulation world name (default: active mission world).",
                    "required": False,
                },
                {
                    "name": "vehicle",
                    "description": "Target drone model (default: active vehicle).",
                    "required": False,
                },
            ],
            "template": """You are an Autonomous Flight Engineer operating SkyTrack Mission Studio.
Assignment: {assignment}
Target World: {world}
Target Vehicle: {vehicle}

Execute the rigorous Closed-Loop Autonomous Flight Workflow:
1. UNDERSTAND: Parse all requirements into a structured checklist (area, altitude, actions, safety, end action).
2. OBSERVE: Call `skytrack_get_context` to inspect active project, mission, vehicle, and simulator readiness.
3. INSPECT WORLD: Call `skytrack_inspect_world` to extract 3D obstacles and 2D occupancy grid slice at target altitude.
4. PLAN & COLLISION CHECK: Construct safe 3D waypoints and verify with `skytrack_validate_mission` and `check_route_collisions`.
5. APPLY: Save route via `skytrack_set_mission` or `draw_route_on_map`, and optionally write Python script via `write_and_save_uav_script`.
6. SIMULATE & OBSERVE: Launch via `skytrack_simulation_start` or `run_mission_and_wait_completion`. Monitor flight progress until drone touches down safely.
7. HARVEST & VERIFY: Read report via `skytrack_report_read` and compile verification matrix against initial requirements.
8. REPAIR: If any requirement failed, diagnose root cause, adjust route, and re-run until verified.
""",
        },
        "skytrack-inspect-world": {
            "name": "skytrack-inspect-world",
            "description": "Inspect 3D Gazebo environment, obstacles, racks, and clearance corridors at flight altitude.",
            "arguments": [
                {
                    "name": "world_name",
                    "description": "Gazebo world name (e.g. 'warehouse', 'farm-petersburg', 'default', 'city').",
                    "required": True,
                },
                {
                    "name": "altitude_m",
                    "description": "Flight slice altitude in meters (default: 2.5).",
                    "required": False,
                },
            ],
            "template": """Inspect the 3D world '{world_name}' at altitude {altitude_m}m.
Use `skytrack_inspect_world` to review all physical collision geometries, bounding boxes, and 2D top-down ASCII map slices.
Identify safe traversable corridors, obstacle boundaries, and optimal spawn/landing areas.
""",
        },
        "skytrack-debug-mission": {
            "name": "skytrack-debug-mission",
            "description": "Diagnose a failing or stuck mission, analyze errors, and repair route/code.",
            "arguments": [
                {
                    "name": "mission_id",
                    "description": "Target mission ID to debug.",
                    "required": False,
                },
            ],
            "template": """Investigate and repair mission '{mission_id}'.
1. Check diagnostics with `skytrack_diagnostics` and `skytrack_logs`.
2. Inspect latest flight report with `skytrack_report_read`.
3. Validate mission structure with `skytrack_validate_mission`.
4. Isolate root cause (collision, timeout, vehicle payload limit, low battery).
5. Apply minimum viable patch with `skytrack_patch_mission` and re-verify.
""",
        },
        "skytrack-review-route": {
            "name": "skytrack-review-route",
            "description": "Statically review candidate route waypoints against vehicle limits and 3D terrain.",
            "arguments": [
                {
                    "name": "world_name",
                    "description": "World name to check against.",
                    "required": True,
                },
                {
                    "name": "waypoints_json",
                    "description": "JSON array of [[x, y, z], ...] waypoints in local ENU meters.",
                    "required": True,
                },
            ],
            "template": """Perform static safety review for candidate waypoints in world '{world_name}':
Waypoints: {waypoints_json}
Check 3D collision freedom, leg distances, climb rates, and proximity to obstacles.
""",
        },
        "skytrack-explain-report": {
            "name": "skytrack-explain-report",
            "description": "Analyze an official SkyTrack flight report and provide executive summary.",
            "arguments": [
                {
                    "name": "mission_id",
                    "description": "Mission ID to evaluate report for.",
                    "required": False,
                },
            ],
            "template": """Read and evaluate flight report for mission '{mission_id}' using `skytrack_report_read`.
Synthesize: flight duration, completion status, payload events executed, battery consumed, and requirement pass/fail verdicts.
""",
        },
    }
