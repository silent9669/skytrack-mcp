from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from skytrack_mcp.mission.parser import canonical_to_ui_dicts, parse_ui_mission
from skytrack_mcp.mission.patcher import MissionPatcher


def multi_sequence_mission() -> tuple[dict[str, Any], dict[str, Any]]:
    mission = {
        "name": "Survey",
        "world": {"name": "warehouse", "revision": 4},
        "vehicle": {"name": "x500_tennis_balls", "payload": "custom"},
        "end": {"id": "end-1", "type": "rtl", "custom": {"keep": True}},
        "codeMode": False,
        "takeoffAltitude": 3.5,
        "targetSpeed": 4.25,
        "safetyOption": "brake",
        "metadataExtension": {"owner": "test"},
    }
    plan = {
        "spawnLocation": [1.0, 2.0, 0.0],
        "planExtension": {"keep": [1, 2]},
        "sequences": [
            {
                "id": "sequence-1",
                "type": "route",
                "targetSpeed": 4.25,
                "sequenceExtension": "first",
                "actions": [
                    {"id": "takeoff-1", "type": "takeoff", "custom": "standalone"},
                    {"id": "navigate-1", "type": "navigate", "data": [5, 6, 7], "custom": 1},
                    {"id": "drop-1", "type": "drop-ball", "payload": "left"},
                ],
            },
            {
                "id": "sequence-2",
                "type": "route",
                "targetSpeed": 1.5,
                "sequenceExtension": "second",
                "actions": [
                    {"id": "navigate-2", "type": "navigate", "data": [8, 9, 10]},
                    {"id": "snapshot-2", "type": "take-snapshot", "camera": "down"},
                    {"id": "rtl-2", "type": "rtl"},
                ],
            },
        ],
    }
    return mission, plan


def test_parse_serialize_unchanged_mission_is_lossless() -> None:
    mission_json, plan_json = multi_sequence_mission()
    canonical = parse_ui_mission("project-1", "mission-1", mission_json, plan_json)

    serialized_plan, serialized_mission = canonical_to_ui_dicts(canonical)

    assert serialized_plan == plan_json
    assert serialized_mission == mission_json
    assert [waypoint.id for waypoint in canonical.waypoints] == ["navigate-1", "navigate-2"]
    assert canonical.waypoints[0].after_action == "drop-ball"
    assert canonical.waypoints[1].after_action == "take-snapshot"
    assert canonical.raw_plan == plan_json
    assert canonical.raw_mission == mission_json
    assert "raw_plan" not in canonical.model_dump()
    assert "raw_mission" not in canonical.model_dump()


def test_parser_keeps_deep_copies_of_ui_documents() -> None:
    mission_json, plan_json = multi_sequence_mission()
    canonical = parse_ui_mission("project-1", "mission-1", mission_json, plan_json)

    mission_json["metadataExtension"]["owner"] = "changed"
    plan_json["sequences"][0]["actions"][1]["data"][0] = 999

    assert canonical.raw_mission["metadataExtension"]["owner"] == "test"
    assert canonical.raw_plan["sequences"][0]["actions"][1]["data"] == [5, 6, 7]


def test_metadata_patch_retains_extra_sequences_and_unknown_fields(tmp_path: Path) -> None:
    mission_json, plan_json = multi_sequence_mission()
    mission_dir = tmp_path / "prj-project-1" / "mis-mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(json.dumps(mission_json), encoding="utf-8")
    (mission_dir / "plan.json").write_text(json.dumps(plan_json), encoding="utf-8")

    patched, _ = MissionPatcher(mission_dir).patch_mission({"world": "city"})

    saved_mission = json.loads((mission_dir / "mission.json").read_text(encoding="utf-8"))
    saved_plan = json.loads((mission_dir / "plan.json").read_text(encoding="utf-8"))
    expected_mission = copy.deepcopy(mission_json)
    if isinstance(expected_mission.get("world"), dict):
        expected_mission["world"]["name"] = "city"
    else:
        expected_mission["world"] = "city"
    assert patched.raw_plan == plan_json
    assert saved_plan == plan_json
    assert saved_mission == expected_mission
    assert saved_mission["world"]["revision"] == 4


def test_waypoint_overwrite_refuses_multi_sequence_before_snapshot_or_write(tmp_path: Path) -> None:
    mission_json, plan_json = multi_sequence_mission()
    mission_dir = tmp_path / "prj-project-1" / "mis-mission-1"
    mission_dir.mkdir(parents=True)
    mission_path = mission_dir / "mission.json"
    plan_path = mission_dir / "plan.json"
    mission_path.write_text(json.dumps(mission_json), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_json), encoding="utf-8")
    original_files = (mission_path.read_bytes(), plan_path.read_bytes())
    patcher = MissionPatcher(mission_dir)

    with pytest.raises(ValueError, match="^UNSUPPORTED_PLAN_SHAPE$"):
        patcher.patch_mission({"set_waypoints": []})

    assert (mission_path.read_bytes(), plan_path.read_bytes()) == original_files
    assert not patcher.backup_dir.exists()


def test_single_sequence_waypoint_patch_retains_standalone_action_and_ids(tmp_path: Path) -> None:
    mission_json = {"world": "warehouse", "end": {"id": "end-id", "type": "rtl"}}
    plan_json = {
        "spawnLocation": [0, 0, 0],
        "vendorData": {"unchanged": True},
        "sequences": [
            {
                "id": "route-id",
                "type": "route",
                "actions": [
                    {"id": "takeoff-id", "type": "takeoff", "vendor": "preserve"},
                    {"id": "wp-id", "type": "navigate", "data": [1, 2, 3], "vendor": 7},
                    {"id": "custom-id", "type": "custom-action", "payload": {"x": 1}},
                ],
            }
        ],
    }
    mission_dir = tmp_path / "prj-project-1" / "mis-mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(json.dumps(mission_json), encoding="utf-8")
    (mission_dir / "plan.json").write_text(json.dumps(plan_json), encoding="utf-8")

    MissionPatcher(mission_dir).patch_mission(
        {"set_waypoints": [{"id": "wp-id", "x": 11, "y": 12, "z": 13}]}
    )
    updated_plan = json.loads((mission_dir / "plan.json").read_text(encoding="utf-8"))
    actions = updated_plan["sequences"][0]["actions"]

    assert updated_plan["vendorData"] == plan_json["vendorData"]
    assert updated_plan["sequences"][0]["id"] == "route-id"
    assert actions[0] == plan_json["sequences"][0]["actions"][0]
    assert actions[1] == {
        "id": "wp-id",
        "type": "navigate",
        "data": [11, 12, 13],
        "vendor": 7,
    }
    assert actions[2] == plan_json["sequences"][0]["actions"][2]
