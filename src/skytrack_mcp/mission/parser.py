"""Parses and serializes between CanonicalMission, SkyTrack UI JSONs, and GCS API payloads."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from skytrack_mcp.mission.models import (
    CanonicalMission,
    Waypoint,
)


def parse_ui_mission(
    project_id: str,
    mission_id: str,
    mission_dict: dict[str, Any],
    plan_dict: dict[str, Any],
    script_text: str = "",
) -> CanonicalMission:
    """Parse SkyTrack's mission.json and plan.json into a CanonicalMission domain object."""
    sequences = plan_dict.get("sequences", [])
    raw_actions = []
    for seq in sequences:
        raw_actions.extend(seq.get("actions", []))

    waypoints: list[Waypoint] = []
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
        raw_actions=copy.deepcopy(raw_actions),
        raw_plan=copy.deepcopy(plan_dict),
        raw_mission=copy.deepcopy(mission_dict),
        python_script=script_text or None,
    )


def _waypoints_match_raw(mission: CanonicalMission, baseline: CanonicalMission) -> bool:
    if len(mission.waypoints) != len(baseline.waypoints):
        return False
    raw_navigation_ids = [
        action.get("id")
        for action in mission.raw_actions
        if action.get("type", "navigate") == "navigate"
        and isinstance(action.get("data"), list)
    ]
    for index, (current, original) in enumerate(zip(mission.waypoints, baseline.waypoints)):
        if (current.x, current.y, current.z, current.after_action) != (
            original.x,
            original.y,
            original.z,
            original.after_action,
        ):
            return False
        if (
            index < len(raw_navigation_ids)
            and raw_navigation_ids[index] is not None
            and current.id != original.id
        ):
            return False
    return True


def _updated_actions(
    original_actions: list[dict[str, Any]], waypoints: list[Waypoint]
) -> list[dict[str, Any]]:
    """Replace route waypoints while retaining unrelated action payloads and IDs."""
    attached_types = {
        "drop-ball",
        "take-snapshot",
        "start-recording-video",
        "stop-recording-video",
        "start-spraying",
        "stop-spraying",
    }
    records_by_id: dict[str, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    records_without_id: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    standalone_by_gap: dict[int, list[dict[str, Any]]] = {}
    navigation_count = 0
    index = 0
    while index < len(original_actions):
        action = original_actions[index]
        if action.get("type", "navigate") == "navigate" and isinstance(
            action.get("data"), list
        ):
            attached = None
            index += 1
            if index < len(original_actions) and original_actions[index].get("type") in attached_types:
                attached = copy.deepcopy(original_actions[index])
                index += 1
            record = (copy.deepcopy(action), attached)
            action_id = action.get("id")
            if action_id:
                records_by_id[str(action_id)] = record
            else:
                records_without_id.append(record)
            navigation_count += 1
            continue
        standalone_by_gap.setdefault(navigation_count, []).append(copy.deepcopy(action))
        index += 1

    updated: list[dict[str, Any]] = []
    for position, waypoint in enumerate(waypoints):
        updated.extend(standalone_by_gap.pop(position, []))
        record = records_by_id.pop(waypoint.id, None)
        if record is None:
            waypoint_coords = [round(waypoint.x, 3), round(waypoint.y, 3), round(waypoint.z, 3)]
            record_index = next(
                (
                    record_index
                    for record_index, (old_action, _) in enumerate(records_without_id)
                    if [round(float(value), 3) for value in old_action["data"][:3]]
                    == waypoint_coords
                ),
                None,
            )
            if record_index is not None:
                record = records_without_id.pop(record_index)

        old_navigation, old_attached = record if record is not None else ({}, None)
        navigate = copy.deepcopy(old_navigation)
        navigate.update(
            {
                "type": "navigate",
                "id": waypoint.id or old_navigation.get("id") or str(uuid.uuid4()),
                "data": [round(waypoint.x, 3), round(waypoint.y, 3), round(waypoint.z, 3)],
            }
        )
        updated.append(navigate)
        if waypoint.after_action:
            attached = copy.deepcopy(old_attached) if old_attached is not None else {}
            attached.update({"type": waypoint.after_action})
            attached.setdefault("id", str(uuid.uuid4()))
            updated.append(attached)

    for standalone in standalone_by_gap.values():
        updated.extend(standalone)
    for old_navigation, old_attached in records_without_id:
        updated.append(old_navigation)
        if old_attached is not None:
            updated.append(old_attached)
    return updated


def canonical_to_ui_dicts(mission: CanonicalMission) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert CanonicalMission into loss-preserving plan.json and mission.json dictionaries."""
    plan_dict = copy.deepcopy(mission.raw_plan)
    mission_dict = copy.deepcopy(mission.raw_mission)

    baseline = parse_ui_mission(
        mission.project_id,
        mission.mission_id,
        mission.raw_mission,
        mission.raw_plan,
    )
    has_raw_plan = bool(mission.raw_plan)
    has_raw_mission = bool(mission.raw_mission)
    waypoints_unchanged = has_raw_plan and _waypoints_match_raw(mission, baseline)

    if not plan_dict:
        plan_dict = {}
    sequences = plan_dict.get("sequences")
    if not isinstance(sequences, list):
        sequences = []
    if not waypoints_unchanged:
        if len(sequences) > 1:
            raise ValueError("UNSUPPORTED_PLAN_SHAPE")
        if sequences:
            sequence = copy.deepcopy(sequences[0])
            sequence["actions"] = _updated_actions(
                sequence.get("actions", []), mission.waypoints
            )
            sequence["targetSpeed"] = float(mission.target_speed)
            sequences[0] = sequence
        else:
            sequences = [
                {
                    "id": str(uuid.uuid4()),
                    "type": "route",
                    "targetSpeed": float(mission.target_speed),
                    "actions": _updated_actions([], mission.waypoints),
                }
            ]
        plan_dict["sequences"] = sequences
    elif mission.target_speed != baseline.target_speed and sequences:
        sequence = copy.deepcopy(sequences[0])
        sequence["targetSpeed"] = float(mission.target_speed)
        sequences[0] = sequence
        plan_dict["sequences"] = sequences

    if (
        mission.spawn_location != baseline.spawn_location
        or (not has_raw_plan and "spawnLocation" not in plan_dict)
    ):
        plan_dict["spawnLocation"] = list(mission.spawn_location)

    if mission.world != baseline.world or not has_raw_mission:
        original_world = mission_dict.get("world")
        if isinstance(original_world, dict):
            original_world["name"] = mission.world
            mission_dict["world"] = original_world
        else:
            mission_dict["world"] = mission.world
    if mission.vehicle != baseline.vehicle or not has_raw_mission:
        original_vehicle = mission_dict.get("vehicle")
        if isinstance(original_vehicle, dict):
            original_vehicle["name"] = mission.vehicle
            mission_dict["vehicle"] = original_vehicle
        else:
            mission_dict["vehicle"] = mission.vehicle
    if mission.name != baseline.name or not has_raw_mission:
        mission_dict["name"] = mission.name

    original_end = mission_dict.get("end", {})
    if not isinstance(original_end, dict):
        original_end = {}
    end = copy.deepcopy(original_end)
    if mission.end_action != baseline.end_action or not has_raw_mission:
        end["type"] = mission.end_action
        if "id" not in end:
            end["id"] = str(uuid.uuid4())
        mission_dict["end"] = end

    canonical_metadata = (
        ("codeMode", bool(mission.code_mode), baseline.code_mode),
        ("takeoffAltitude", float(mission.takeoff_altitude), baseline.takeoff_altitude),
        ("safetyOption", mission.safety_option, baseline.safety_option),
        ("targetSpeed", float(mission.target_speed), baseline.target_speed),
    )
    for key, value, original_value in canonical_metadata:
        if value != original_value or not has_raw_mission:
            mission_dict[key] = value

    return plan_dict, mission_dict


def canonical_to_gcs_payload(mission: CanonicalMission) -> dict[str, Any]:
    """Convert CanonicalMission to the FrontendMissionExecutionRequest schema for GCS :20002."""
    actions: list[dict[str, Any]] = []
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
        item: dict[str, Any] = {
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
