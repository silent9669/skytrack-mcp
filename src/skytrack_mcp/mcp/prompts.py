"""MCP Prompt templates for standard autonomous SkyTrack workflows."""

from __future__ import annotations

from typing import Any


def get_prompt_templates() -> dict[str, dict[str, Any]]:
    return {
        "skytrack-solve-mission": {
            "name": "skytrack-solve-mission",
            "description": "Inspect and statically validate a SkyTrack mission against environment and vehicle constraints.",
            "arguments": [
                {
                    "name": "assignment",
                    "description": "Natural language mission assignment (e.g. inspect warehouse aisles, scan crops).",
                    "required": True,
                },
                {
                    "name": "project",
                    "description": "Target project name or ID.",
                    "required": False,
                },
                {
                    "name": "mission",
                    "description": "Target mission name or ID.",
                    "required": False,
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
Target Project: {project}
Target Mission: {mission}
Target World: {world}
Target Vehicle: {vehicle}

Execute the Phase 1 Target Resolution, World Inspection, and Static Validation Workflow:
1. UNDERSTAND: Parse all requirements into a structured checklist (area, altitude, safety, constraints).
2. RESOLVE TARGET: Call `tool_skytrack_resolve_target` with project_name_or_id='{project}' and mission_name_or_id='{mission}' to resolve exact project and mission IDs. If status is MISSING or AMBIGUOUS, request clarification or confirmation before proceeding.
3. VERIFY PERMISSION: Call `tool_skytrack_check_permission` with the resolved project_id and mission_id to verify edit rights before authoring; respect view-only locks.
4. INSPECT WORLD: Call `tool_skytrack_inspect_world` to extract 3D obstacles and 2D occupancy grid slice at target altitude.
5. VALIDATE MISSION & ROUTE: Inspect the resolved mission via `tool_skytrack_get_mission` and statically verify with `tool_skytrack_validate_mission` and `check_route_collisions`.
6. REVIEW AUTONOMY CONSTRAINTS: Call `get_uav_python_sdk_reference` or `get_autonomy_level_template` to review supported SDK patterns.
(Note: Phase 1 provides read-only inspection and validation. Lossless mission authoring and post-run debug loops are enabled in subsequent phases.)
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
Use `tool_skytrack_inspect_world` to review physical collision geometries, bounding boxes, and 2D top-down ASCII map slices.
Identify safe traversable corridors, obstacle boundaries, and optimal spawn/landing areas.
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
Use `check_route_collisions` to verify 3D clearance against obstacles in '{world_name}'.
To validate against drone vehicle constraints for an existing mission, call `tool_skytrack_validate_mission` with that mission's exact ID.
""",
        },
    }
