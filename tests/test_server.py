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
        "report_provenance": "authentic",
        "execution_status": "Succeeded",
        "landing_completed": True,
        "total_planned_waypoints": 6,
        "waypoints_reached_count": 6,
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


@pytest.mark.asyncio
async def test_mission_wait_refuses_dispatch_without_telemetry(monkeypatch):
    from skytrack_mcp import server

    monkeypatch.setattr(server, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    async def should_not_dispatch(**kwargs):
        raise AssertionError("Disconnected telemetry must prevent flight dispatch")

    monkeypatch.setattr(server, "execute_route_mission", should_not_dispatch)
    result = await server.run_mission_and_wait_completion(mission_id="MIS_TEST")
    assert result["status"] == "simulator_not_ready"


@pytest.mark.asyncio
async def test_mission_wait_observes_flight_after_connected_dispatch(monkeypatch):
    from skytrack_mcp import server

    monkeypatch.setattr(server, "fetch_live_mavlink_telemetry", lambda: {"connected": True})

    async def dispatch(**kwargs):
        return {"ok": True, "response": {"execution_id": "EX1"}}

    monkeypatch.setattr(server, "execute_route_mission", dispatch)
    result = await server.run_mission_and_wait_completion(mission_id="MIS_TEST", max_wait_seconds=0)
    assert result["status"] == "timeout_or_failed"


def test_world_discovery_uses_packaged_sdfs_without_docker(monkeypatch):
    from skytrack_mcp.clients import docker_exec

    assert (Path(docker_exec.__file__).resolve().parents[1] / "worlds" / "warehouse.sdf").is_file()
    monkeypatch.setattr(docker_exec, "_run_cmd", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Docker must not be needed")))
    assert "warehouse" in docker_exec.list_gazebo_worlds()
    assert docker_exec.inspect_world_sdf("warehouse")["world"] == "warehouse"


def test_urban_mesh_is_reported_as_uninspected_collision_geometry(tmp_path, monkeypatch):
    from skytrack_mcp.clients import docker_exec

    (tmp_path / "urban.sdf").write_text(
        '<sdf version="1.9"><world name="urban"><include>'
        '<uri>model://urban</uri></include></world></sdf>'
    )
    monkeypatch.setattr(docker_exec, "LOCAL_WORLD_CACHE_DIR", tmp_path)
    world = inspect_world_map("urban", slice_altitude_m=36)
    route = check_route_collisions("urban", [[200, -80, 36], [110, 10, 36]])
    assert world["geometry_complete"] is False
    assert route["geometry_complete"] is False
    assert route["unresolved_models"] == ["model://urban"]
    assert route["is_collision_free"] is False


def test_inline_mesh_is_reported_as_uninspected_collision_geometry(tmp_path, monkeypatch):
    from skytrack_mcp.clients import docker_exec

    (tmp_path / "mesh-city.sdf").write_text(
        '<sdf version="1.9"><world name="mesh-city"><model name="tower"><link name="body">'
        '<collision name="structure"><geometry><mesh><uri>model://tower/collision.glb</uri>'
        '</mesh></geometry></collision></link></model></world></sdf>'
    )
    monkeypatch.setattr(docker_exec, "LOCAL_WORLD_CACHE_DIR", tmp_path)
    result = check_route_collisions("mesh-city", [[0, 0, 36], [10, 0, 36]])
    assert result["geometry_complete"] is False
    assert result["is_collision_free"] is False


def test_verification_does_not_accept_planned_waypoints_as_flight_evidence():
    report = {
        "report_provenance": "synthetic_only",
        "execution_status": "UNKNOWN",
        "total_planned_waypoints": 6,
        "waypoints_reached_count": 0,
        "telemetry_state": {"connected": False, "landed_state": "ON_GROUND"},
    }
    requirements = [
        {"name": "Safe Landing", "type": "landed_safely", "mandatory": True},
        {"name": "Visited Waypoints", "type": "min_waypoints", "expected": 5, "mandatory": True},
    ]
    result = evaluate_mission_requirements("MIS_TEST", requirements, report)
    assert result.overall_status != VerificationStatus.PASS
    assert all(item.status == VerificationStatus.UNKNOWN for item in result.items)


def test_verification_accepts_native_report_after_telemetry_disconnects():
    report = {
        "report_provenance": "authentic",
        "execution_status": "Succeeded",
        "landing_completed": True,
        "total_planned_waypoints": 6,
        "waypoints_reached_count": 6,
        "telemetry_state": {"connected": False, "landed_state": "UNKNOWN"},
    }
    requirements = [
        {"name": "Safe Landing", "type": "landed_safely", "mandatory": True},
        {"name": "Visited Waypoints", "type": "min_waypoints", "expected": 5, "mandatory": True},
    ]
    result = evaluate_mission_requirements("MIS_TEST", requirements, report)
    assert result.overall_status == VerificationStatus.PASS
    assert all(item.status == VerificationStatus.PASS for item in result.items)


def test_verification_cannot_pass_plan_only_world_altitude_or_missing_collision_result():
    report = {
        "report_provenance": "none", "world": "urban", "takeoff_altitude_m": 36,
        "telemetry_state": {"connected": False},
    }
    requirements = [
        {"name": "World", "type": "world", "expected": "urban"},
        {"name": "Altitude", "type": "takeoff_altitude", "expected": 35},
        {"name": "Collision", "type": "collision_freedom"},
    ]
    result = evaluate_mission_requirements("M1", requirements, report)
    assert result.overall_status != VerificationStatus.PASS
    assert all(item.status == VerificationStatus.UNKNOWN for item in result.items)


def test_native_altitude_below_minimum_does_not_pass():
    report = {"report_provenance": "authentic", "observed_takeoff_altitude_m": 34.95}
    result = evaluate_mission_requirements("M1", [{"name": "Altitude", "type": "takeoff_altitude", "expected": 35}], report)
    assert result.overall_status == VerificationStatus.FAIL


def test_verified_native_altitude_and_complete_geometry_pass():
    report = {
        "report_provenance": "authentic", "observed_takeoff_altitude_m": 36,
        "world": "urban", "telemetry_state": {},
    }
    requirements = [
        {"name": "World", "type": "world", "expected": "urban"},
        {"name": "Altitude", "type": "takeoff_altitude", "expected": 35},
        {"name": "Collision", "type": "collision_freedom", "is_collision_free": True,
         "conflicts": [], "geometry_complete": True},
    ]
    result = evaluate_mission_requirements("M1", requirements, report)
    assert result.overall_status == VerificationStatus.PASS


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


@pytest.mark.parametrize(
    "waypoint",
    [
        {"x": 1.0, "y": 2.0, "z": 3.0, "after_action": "drop-ball"},
        {"type": "drop-ball"},
        {"type": "drop_payload"},
    ],
)
def test_convert_route_rejects_unsupported_ball_drop(waypoint: dict[str, object]):
    with pytest.raises(ValueError, match="local_planner SDK has no ball-drop API"):
        convert_route_to_python_script(waypoints=[waypoint], save_to_mission=False)


def test_unit_draw_route_and_convert_to_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    prj_dir = tmp_path / "prj-TESTPROJECT"
    mis_dir = prj_dir / "mis-TESTMISSION"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(
        json.dumps({"world": "warehouse", "vehicle": "x500_livox_mid_360", "codeMode": True}),
        encoding="utf-8",
    )
    (mis_dir / "plan.json").write_text(
        json.dumps({"spawnLocation": [12.0, -9.0, 0.0], "sequences": []}),
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

    with pytest.raises(ValueError, match="drop-ball"):
        convert_route_to_python_script(
            mission_id="TESTMISSION",
            save_to_mission=False,
        )

    conv_res = convert_route_to_python_script(
        waypoints=[
            {"x": 2.5, "y": 3.0, "z": 2.0, "after_action": "take-photo"},
            {"x": 0.0, "y": 0.0, "z": 2.0},
        ],
        mission_id="TESTMISSION",
        takeoff_altitude=2.0,
        save_to_mission=False,
    )
    assert "yield takeoff(alt_m=2.00)" in conv_res["python_code"]
    assert "yield capture(" in conv_res["python_code"]
    assert "fly_to(north=-9.000, east=12.000, alt_m=2.00, name='return_home')" in conv_res["python_code"]
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
