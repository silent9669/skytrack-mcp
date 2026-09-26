"""MCP Resource definitions (skytrack://...) for static and contextual knowledge."""

from __future__ import annotations

import json
from typing import Any, Dict

from skytrack_mcp.clients.docker_exec import list_gazebo_worlds
from skytrack_mcp.clients.storage_sync import list_all_missions, read_mission_details
from skytrack_mcp.core.errors import SkyTrackErrorCode
from skytrack_mcp.mission.validator import VEHICLE_CAPABILITIES
from skytrack_mcp.report.parser import harvest_mission_report_data, render_markdown_flight_report


def get_operator_guide_resource() -> str:
    return """# SkyTrack Mission Studio — Autonomous Agent Operator Guide

1. Architecture Overview:
   - SkyTrack is an autonomous drone mission engineering environment.
   - Simulation uses Gazebo Harmonic (3D physics/sensors) + PX4 Autopilot (flight controller).
   - Mission Edge Computer runs ROS 2 Jazzy with payload and mission nodes.
   - SkyTrack Autonomy runs Python scripts using the `local_planner` SDK.

2. Coordinate Conventions:
   - Visual Map & UI (plan.json): ENU (East-North-Up) in meters.
   - Drone Autopilot & Wire: NED (North-East-Down) in meters.
   - Python SDK: fly_to(north=Y, east=X, alt_m=Z).

3. Standard Autonomous Loop:
   Understand Assignment -> Inspect World -> Plan Route -> Validate -> Apply -> Simulate -> Observe -> Harvest Report -> Verify.
"""


def get_mission_schema_resource() -> str:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SkyTrackMission",
        "type": "object",
        "required": ["world", "vehicle", "plan"],
        "properties": {
            "world": {"type": "string"},
            "vehicle": {"type": "string"},
            "takeoffAltitude": {"type": "number", "minimum": 1.0, "maximum": 50.0},
            "targetSpeed": {"type": "number", "minimum": 0.5, "maximum": 12.0},
            "safetyOption": {"type": "string", "enum": ["avoid", "brake", "off"]},
            "end": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["rtl", "land"]},
                },
                "required": ["type"],
            },
            "plan": {
                "type": "object",
                "required": ["spawnLocation", "sequences"],
                "properties": {
                    "spawnLocation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                    "sequences": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "actions": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["type"],
                                        "properties": {
                                            "type": {"type": "string"},
                                            "data": {"type": "array"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    return json.dumps(schema, indent=2)


def get_worlds_resource() -> str:
    worlds = list_gazebo_worlds()
    return json.dumps({"available_worlds": worlds, "total_worlds": len(worlds)}, indent=2)


def get_vehicles_resource() -> str:
    return json.dumps({"vehicles": VEHICLE_CAPABILITIES}, indent=2)


def get_errors_catalog_resource() -> str:
    catalog = {
        code.value: {
            "code": code.value,
            "description": f"Standard SkyTrack error for {code.name}",
        }
        for code in SkyTrackErrorCode
    }
    return json.dumps(catalog, indent=2)


def get_capabilities_resource() -> str:
    caps = {
        "mcp_version": "0.1.0",
        "skytrack_app_supported": "1.2.2",
        "features": [
            "3D Gazebo SDF Inspection & Obstacle Bounding Box Extraction",
            "2D Top-Down ASCII Occupancy Map Slices at Arbitrary Altitudes",
            "3D Slab-Method Route Collision Detection & Safety Inflation",
            "Path Planner API Integration (:20007) with No-Fly Zone Splitting",
            "Direct GCS Control & Flight Commands (:20002)",
            "Live MAVLink Bridge Telemetry (10 Hz WebSocket / State Cache)",
            "SkyTrack Cloud Platform Integration (BFF Projects & Missions)",
            "Transactional Local Storage Synchronization (plan.json / mission.json / script.py)",
            "Automated Docker Simulation Lifecycle (7 containers)",
            "Python Autonomy Scripting (local_planner SDK with AST validation)",
            "Autonomous Polling & State Detection Loop",
            "Flight Report Harvesting & Requirement Verification Matrix",
            "macOS Window Detection, Focus & Screencapture Fallbacks",
        ],
    }
    return json.dumps(caps, indent=2)


def get_current_mission_resource() -> str:
    missions = list_all_missions()
    if not missions:
        return json.dumps({"error": "No mission currently open in ClientData."})
    details = read_mission_details(missions[0]["mission_id"])
    return json.dumps(details, indent=2)


def get_current_report_resource() -> str:
    missions = list_all_missions()
    if not missions:
        return "# No active mission available for report."
    active = missions[0]
    data = harvest_mission_report_data(active["mission_id"], active["project_id"])
    return render_markdown_flight_report(data)
