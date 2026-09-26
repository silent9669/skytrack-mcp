"""Parses and serializes between CanonicalMission, SkyTrack UI JSONs, and GCS API payloads."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from skytrack_mcp.mission.models import (
    CanonicalMission,
    Waypoint,
)


def parse_ui_mission(
    project_id: str,
    mission_id: str,
    mission_dict: Dict[str, Any],
    plan_dict: Dict[str, Any],
    script_text: str = "",
) -> CanonicalMission:
    """Parse SkyTrack's mission.json and plan.json into a CanonicalMission domain object."""
    sequences = plan_dict.get("sequences", [])
    raw_actions = []
    for seq in sequences:
        raw_actions.extend(seq.get("actions", []))

    waypoints: List[Waypoint] = []
    i = 0
    while i < len(raw_actions):
        act = raw_actions[i]
        act_type = act.get("type", "navigate")
        if act_type == "navigate" and "data" in act and isinstance(act["data"], list):
            coords = act["data"]
            z_val = coords[2] if len(coords) >= 3 else mission_dict.get("takeoffAltitude", 2.5)
            wp = Waypoint(
                id=str(act.get("id") or uuid.uuid4()),
                x=float(coords[0]),
                y=float(coords[1]),
                z=float(z_val),
            )
            # Check if next action is an attached payload or camera action
            if i + 1 < len(raw_actions):
                next_act = raw_actions[i + 1]
                next_type = next_act.get("type", "")
                if next_type in (
                    "drop-ball",
                    "take-snapshot",
                    "start-recording-video",
                    "stop-recording-video",
                    "start-spraying",
                    "stop-spraying",
                ):
                    wp.after_action = next_type
                    i += 1
            waypoints.append(wp)
        i += 1

    spawn = plan_dict.get("spawnLocation", [0.0, 0.0, 0.0])
    if not isinstance(spawn, list) or len(spawn) < 3:
        spawn = [0.0, 0.0, 0.0]

    end_action = mission_dict.get("end", {}).get("type", "rtl")
    if end_action not in ("rtl", "land"):
        end_action = "rtl"

    world = mission_dict.get("world", "default")
    if isinstance(world, dict):
        world = world.get("name", "default")
    world = str(world or "default")

    vehicle = mission_dict.get("vehicle", "x500_livox_mid_360")
    if isinstance(vehicle, dict):
        vehicle = vehicle.get("name", "x500_livox_mid_360")
    vehicle = str(vehicle or "x500_livox_mid_360")

    return CanonicalMission(
        project_id=project_id,
        mission_id=mission_id,
        name=mission_dict.get("name", f"Mission {mission_id}"),
        world=world,
        vehicle=vehicle,
        code_mode=bool(mission_dict.get("codeMode", False)),
        takeoff_altitude=float(mission_dict.get("takeoffAltitude", 2.5)),
        target_speed=float(mission_dict.get("targetSpeed", 2.0)),
        safety_option=mission_dict.get("safetyOption", "avoid"),
        end_action=end_action,
        spawn_location=[float(s) for s in spawn[:3]],
        waypoints=waypoints,
        raw_actions=raw_actions,
        python_script=script_text or None,
    )


def canonical_to_ui_dicts(mission: CanonicalMission) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Convert CanonicalMission into (plan.json_dict, mission.json_dict) for SkyTrack UI."""
    actions: List[Dict[str, Any]] = []
    for wp in mission.waypoints:
        actions.append(
            {
                "type": "navigate",
                "id": wp.id or str(uuid.uuid4()),
                "data": [round(wp.x, 3), round(wp.y, 3), round(wp.z, 3)],
            }
        )
        if wp.after_action:
            actions.append(
                {
                    "type": wp.after_action,
                    "id": str(uuid.uuid4()),
                }
            )

    plan_dict = {
        "spawnLocation": mission.spawn_location,
        "sequences": [
            {
                "id": str(uuid.uuid4()),
                "type": "route",
                "targetSpeed": float(mission.target_speed),
                "actions": actions,
            }
        ],
    }

    mission_dict = {
        "world": mission.world,
        "vehicle": mission.vehicle,
        "end": {
            "id": str(uuid.uuid4()),
            "type": mission.end_action,
        },
        "codeMode": bool(mission.code_mode),
        "takeoffAltitude": float(mission.takeoff_altitude),
        "safetyOption": mission.safety_option,
        "targetSpeed": float(mission.target_speed),
    }

    return plan_dict, mission_dict


def canonical_to_gcs_payload(mission: CanonicalMission) -> Dict[str, Any]:
    """Convert CanonicalMission to the FrontendMissionExecutionRequest schema for GCS :20002."""
    actions: List[Dict[str, Any]] = []
    for wp in mission.waypoints:
        actions.append(
            {
                "id": str(uuid.uuid4()),
                "type": "navigation",
                "frame": "enu",
                "x": float(wp.x),
                "y": float(wp.y),
                "z": float(wp.z),
                "target_speed": float(wp.target_speed or mission.target_speed),
            }
        )
        if wp.after_action == "drop-ball":
            actions.append({"id": str(uuid.uuid4()), "type": "drop_payload"})
        elif wp.after_action == "take-snapshot":
            actions.append(
                {"id": str(uuid.uuid4()), "type": "camera_trigger", "operation": "snapshot"}
            )
        elif wp.after_action == "start-recording-video":
            actions.append(
                {"id": str(uuid.uuid4()), "type": "camera_trigger", "operation": "recording_on"}
            )
        elif wp.after_action == "stop-recording-video":
            actions.append(
                {"id": str(uuid.uuid4()), "type": "camera_trigger", "operation": "recording_off"}
            )
        elif wp.after_action == "start-spraying":
            actions.append({"id": str(uuid.uuid4()), "type": "spray", "operation": "on"})
        elif wp.after_action == "stop-spraying":
            actions.append({"id": str(uuid.uuid4()), "type": "spray", "operation": "off"})

    # Always ensure end action
    if mission.end_action in ("rtl", "land"):
        actions.append({"id": str(uuid.uuid4()), "type": mission.end_action})

    nfz_payload = []
    for z in mission.no_fly_zones:
        item: Dict[str, Any] = {
            "id": z.id,
            "frame": z.frame,
            "units": "m",
            "inclusion": z.inclusion,
            "z_range": [z.z_min, z.z_max],
        }
        if z.circle:
            item["circle"] = {"center": list(z.center or (0, 0)), "radius": float(z.radius or 10.0)}
        elif z.polygon:
            item["polygon"] = [list(pt) for pt in z.polygon]
        nfz_payload.append(item)

    return {
        "actions": actions,
        "settings": {
            "takeoff_altitude": max(1.0, float(mission.takeoff_altitude)),
            "avoidance_mode": mission.safety_option if mission.safety_option in ("avoid", "brake") else "avoid",
            "smart": True,
            "no_fly_zones": nfz_payload,
        },
    }
