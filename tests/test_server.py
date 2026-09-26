"""Unit and Integration Tests for SkyTrack MCP Server."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from skytrack_mcp.mission.models import CanonicalMission, ValidationSeverity, Waypoint
from skytrack_mcp.mission.parser import canonical_to_gcs_payload, canonical_to_ui_dicts, parse_ui_mission
from skytrack_mcp.mission.patcher import MissionPatcher
from skytrack_mcp.mission.validator import validate_canonical_mission
from skytrack_mcp.report.verification import VerificationStatus, evaluate_mission_requirements
from skytrack_mcp.route.geometry_utils import compute_route_metrics, verify_route_collision_freedom
from skytrack_mcp.server import (
    check_route_collisions,
    convert_route_to_python_script,
    draw_route_on_map,
    execute_uav_python_script,
    get_mission_state,
    get_uav_python_sdk_reference,
    get_uav_script_logs,
    get_uav_telemetry,
    inspect_world_map,
    list_missions_and_worlds,
    plan_coverage_route,
    stop_uav_python_script,
    validate_uav_python_code,
    write_and_save_uav_script,
)


def test_unit_canonical_mission_model():
    m = CanonicalMission(
        project_id="PRJ1",
        mission_id="MIS1",
        world="warehouse",
        vehicle="x500_tennis_balls_no_cam",
        takeoff_altitude=3.5,
        target_speed=2.0,
        waypoints=[
            Waypoint(x=1.0, y=2.0, z=3.5, after_action="drop-ball"),
            Waypoint(x=3.0, y=2.0, z=3.5),
        ],
    )
    assert m.world == "warehouse"
    assert len(m.waypoints) == 2
    assert m.waypoints[0].after_action == "drop-ball"

    plan_d, mis_d = canonical_to_ui_dicts(m)
    assert plan_d["sequences"][0]["actions"][0]["type"] == "navigate"
    assert plan_d["sequences"][0]["actions"][1]["type"] == "drop-ball"

    gcs_payload = canonical_to_gcs_payload(m)
    assert gcs_payload["actions"][0]["type"] == "navigation"
    assert gcs_payload["actions"][1]["type"] == "drop_payload"
    assert gcs_payload["settings"]["takeoff_altitude"] == 3.5


def test_unit_static_validator():
    # 1. Invalid altitude (< 1.0m)
    m_bad_alt = CanonicalMission(
        project_id="P1",
        mission_id="M1",
        takeoff_altitude=0.5,
        waypoints=[Waypoint(x=1, y=1, z=0.5)],
    )
    val1 = validate_canonical_mission(m_bad_alt)
    assert val1.valid is False
    assert any(i.code == "INVALID_TAKEOFF_ALTITUDE" for i in val1.issues)

    # 2. Dropping balls exceeding vehicle capacity
    m_excess_balls = CanonicalMission(
        project_id="P1",
        mission_id="M1",
        vehicle="x500_tennis_balls_no_cam",  # capacity 5
        takeoff_altitude=2.5,
        waypoints=[
            Waypoint(x=i, y=0, z=2.5, after_action="drop-ball") for i in range(6)
        ],
    )
    val2 = validate_canonical_mission(m_excess_balls)
    assert val2.valid is False
    assert any(i.code == "PAYLOAD_CAPACITY_EXCEEDED" for i in val2.issues)

    # 3. Vehicle has no camera but camera snapshot action requested
    m_no_cam = CanonicalMission(
        project_id="P1",
        mission_id="M1",
        vehicle="x500_livox_mid_360",  # no camera
        takeoff_altitude=2.5,
        waypoints=[Waypoint(x=1, y=1, z=2.5, after_action="take-snapshot")],
    )
    val3 = validate_canonical_mission(m_no_cam)
    assert val3.valid is False
    assert any(i.code == "UNSUPPORTED_CAMERA_ACTION" for i in val3.issues)


def test_unit_mission_patcher(tmp_path: Path):
    mis_dir = tmp_path / "prj-P1" / "mis-M1"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(json.dumps({"world": "default", "vehicle": "x500"}), encoding="utf-8")
    (mis_dir / "plan.json").write_text(json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}), encoding="utf-8")

    patcher = MissionPatcher(mis_dir)
    m = patcher.load_canonical()
    assert m.world == "default"

    patched, snap_id = patcher.patch_mission(
        {
            "world": "warehouse",
            "add_waypoints": [{"x": 1.0, "y": 2.0, "z": 3.0}],
        }
    )
    assert patched.world == "warehouse"
    assert len(patched.waypoints) == 1
    assert snap_id != ""

    # Test rollback
    patcher.rollback_to_snapshot(snap_id)
    rolled_back = patcher.load_canonical()
    assert rolled_back.world == "default"
    assert len(rolled_back.waypoints) == 0


def test_unit_route_metrics_and_collision():
    wps = [
        [0.0, 0.0, 3.5],
        [2.63, -1.0, 3.5],
        [2.63, -7.5, 3.5],
        [4.90, -7.5, 3.5],
        [6.90, -7.5, 3.5],
        [2.63, -1.0, 3.5],
        [0.00,  0.0, 3.5],
    ]
    metrics = compute_route_metrics(wps)
    assert metrics["total_distance_m"] > 15.0
    assert metrics["max_alt_m"] == 3.5

    col_res = verify_route_collision_freedom("warehouse", wps, clearance_m=0.3)
    assert col_res["is_collision_free"] is True
    assert len(col_res["conflicts"]) == 0


def test_unit_verification_matrix():
    report_mock = {
        "world": "warehouse",
        "total_planned_waypoints": 6,
        "telemetry_state": {
            "landed_state": "ON_GROUND",
            "battery_percentage": 95.0,
        },
        "media_output": {
            "captures_count": 3,
            "captures": ["img1.jpg", "img2.jpg", "img3.jpg"],
        },
    }
    reqs = [
        {"name": "Safe Landing", "type": "landed_safely", "mandatory": True},
        {"name": "Minimum Waypoints", "type": "min_waypoints", "expected": 5, "mandatory": True},
        {"name": "World Match", "type": "world", "expected": "warehouse", "mandatory": True},
        {"name": "Images Captured", "type": "captures", "expected": 2, "mandatory": True},
        {"name": "Battery Margin", "type": "battery_margin", "expected": 20.0, "mandatory": True},
    ]
    matrix = evaluate_mission_requirements("MIS_TEST", reqs, report_mock)
    assert matrix.overall_status == VerificationStatus.PASS
    assert all(item.status == VerificationStatus.PASS for item in matrix.items)


def test_unit_ast_validation_and_sdk_ref():
    sdk_ref = get_uav_python_sdk_reference()
    assert "boot_drone" in sdk_ref["function_signatures"]

    bad_code = """
from local_planner import boot_drone, takeoff
def scenario(ctx):
    yield takeoff(altitude=3.0)
"""
    val_bad = validate_uav_python_code(bad_code)
    assert val_bad["valid"] is False
    assert any("alt_m" in e for e in val_bad["errors"])

    val_ok = validate_uav_python_code(sdk_ref["example_script"])
    assert val_ok["valid"] is True


def test_unit_draw_route_and_convert_to_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    prj_dir = tmp_path / "prj-TESTPROJECT"
    mis_dir = prj_dir / "mis-TESTMISSION"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(
        json.dumps({"world": "warehouse", "vehicle": "x500_livox_mid_360", "codeMode": True}),
        encoding="utf-8",
    )
    (mis_dir / "plan.json").write_text(
        json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}),
        encoding="utf-8",
    )

    from skytrack_mcp.clients import storage_sync

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)

    draw_res = draw_route_on_map(
        waypoints=[
            {"x": 2.5, "y": 3.0, "z": 2.0, "after_action": "take-photo"},
            {"x": 5.0, "y": 3.0, "z": 2.5, "after_action": "drop-ball"},
            {"x": 0.0, "y": 0.0, "z": 2.0},
        ],
        mission_id="TESTMISSION",
        takeoff_altitude=2.0,
        target_speed=2.5,
    )
    assert draw_res["actions_written"] == 5
    assert draw_res["mission"]["codeMode"] is False

    conv_res = convert_route_to_python_script(
        mission_id="TESTMISSION",
        save_to_mission=True,
    )
    assert "yield takeoff(alt_m=2.00)" in conv_res["python_code"]
    assert "yield capture(" in conv_res["python_code"]
    assert validate_uav_python_code(conv_res["python_code"])["valid"] is True


# =====================================================================
# LIVE SIMULATION & INTEGRATION TESTS (Tagged with live_simulation)
# =====================================================================


@pytest.mark.live_simulation
@pytest.mark.asyncio
async def test_live_1_list_missions_and_worlds():
    res = await list_missions_and_worlds()
    assert "missions" in res
    assert len(res["missions"]) > 0
    assert "warehouse" in res["available_worlds"]
    assert res["active_mission"] is not None


@pytest.mark.live_simulation
@pytest.mark.asyncio
async def test_live_2_telemetry():
    telem = await get_uav_telemetry()
    assert "telemetry" in telem
    assert "connected" in telem["telemetry"]
    assert "landed_state" in telem["telemetry"]


@pytest.mark.live_simulation
@pytest.mark.asyncio
async def test_live_3_plan_coverage_route_api():
    area = [
        {"x": -4.0, "y": -4.0},
        {"x": 4.0, "y": -4.0},
        {"x": 4.0, "y": 4.0},
        {"x": -4.0, "y": 4.0},
    ]
    res = await plan_coverage_route(
        area_coords=area,
        spacing_m=2.5,
        orientation_deg=90.0,
        altitude_m=2.5,
        save_to_mission_ui=False,
    )
    assert res["waypoint_count"] >= 4


@pytest.mark.live_simulation
def test_live_4_container_execution():
    sdk_ref = get_uav_python_sdk_reference()
    exec_res = execute_uav_python_script(
        python_code=sdk_ref["example_script"],
        background=True,
        wait_seconds=1.0,
    )
    assert exec_res["executed"] is True
    stop_res = stop_uav_python_script()
    assert stop_res["stopped"] is True
