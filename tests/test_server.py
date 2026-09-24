"""End-to-End Integration Tests for SkyTrack MCP Server against the live SkyTrack system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.mark.asyncio
async def test_1_list_missions_and_worlds():
    res = await list_missions_and_worlds()
    assert "missions" in res
    assert len(res["missions"]) > 0
    assert "warehouse" in res["available_worlds"]
    assert "default" in res["available_worlds"]
    assert res["active_mission"] is not None


def test_2_inspect_world_map_and_collisions():
    world_data = inspect_world_map(world_name="warehouse", slice_altitude_m=2.5, grid_half_size_m=12.0)
    assert world_data["world"] == "warehouse"
    assert world_data["total_collision_boxes"] > 0
    assert "Top-Down Map Slice" in world_data["ascii_map_2d"]
    assert "S" in world_data["ascii_map_2d"]

    # Test collision checker with safe path vs wall intersection path
    safe_check = check_route_collisions(
        world_name="warehouse",
        waypoints=[[0.0, 0.0, 2.5], [1.0, 0.0, 2.5]],
        clearance_m=0.2,
    )
    assert "is_collision_free" in safe_check

    # Path crossing wall1 at (4.13, -10.02, 3.48)
    wall_check = check_route_collisions(
        world_name="warehouse",
        waypoints=[[4.0, -5.0, 2.5], [4.0, -12.0, 2.5]],
        clearance_m=0.3,
    )
    assert wall_check["is_collision_free"] is False
    assert len(wall_check["conflicts"]) > 0


@pytest.mark.asyncio
async def test_3_live_uav_telemetry():
    telem = await get_uav_telemetry()
    assert "telemetry" in telem
    assert "connected" in telem["telemetry"]
    assert "landed_state" in telem["telemetry"]
    assert "attitude_deg" in telem["telemetry"]


@pytest.mark.asyncio
async def test_4_plan_coverage_route_and_nfz():
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
    assert len(res["waypoints_enu"]) == res["waypoint_count"]


def test_5_draw_route_and_convert_to_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Create an isolated mock ClientData mission directory to verify UI file writing
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


def test_6_ast_validation_and_sdk_ref():
    sdk_ref = get_uav_python_sdk_reference()
    assert "boot_drone" in sdk_ref["function_signatures"]

    # Bad keyword argument `altitude=` instead of `alt_m=`
    bad_code = """
from local_planner import boot_drone, takeoff
def scenario(ctx):
    yield takeoff(altitude=3.0)
"""
    val_bad = validate_uav_python_code(bad_code)
    assert val_bad["valid"] is False
    assert any("alt_m" in e for e in val_bad["errors"])

    # Valid template
    val_ok = validate_uav_python_code(sdk_ref["example_script"])
    assert val_ok["valid"] is True


def test_7_container_python_execution_and_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    prj_dir = tmp_path / "prj-EXEC"
    mis_dir = prj_dir / "mis-EXEC1"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(json.dumps({"world": "default"}), encoding="utf-8")

    from skytrack_mcp.clients import storage_sync

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)

    # A quick non-blocking verification script that imports local_planner inside the container
    probe_script = '''"""Verify local_planner SDK inside skytrack-autonomy container."""
import local_planner
from local_planner import boot_drone, takeoff, fly_to, land

def scenario(ctx):
    yield takeoff(alt_m=2.0)
    yield land()

scenario.requires_senses = ["pose", "obstacle", "status"]

if __name__ == "__main__":
    print("SKYTRACK_MCP_CONTAINER_SDK_OK:", hasattr(local_planner, "boot_drone"))
'''
    save_res = write_and_save_uav_script(python_code=probe_script, mission_id="EXEC1")
    assert save_res["saved"] is True

    exec_res = execute_uav_python_script(
        python_code=probe_script,
        mission_id="EXEC1",
        background=False,
        wait_seconds=10.0,
    )
    assert exec_res["executed"] is True
    assert "SKYTRACK_MCP_CONTAINER_SDK_OK: True" in exec_res["stdout"]

    stop_res = stop_uav_python_script()
    assert stop_res["stopped"] is True
    logs_res = get_uav_script_logs(tail_lines=20)
    assert "state" in logs_res


def test_8_cloud_and_closed_loop_management():
    from skytrack_mcp.server import (
        harvest_flight_report,
        list_skytrack_cloud_projects,
        manage_simulation_stack,
    )

    # 1. Cloud projects
    projects = list_skytrack_cloud_projects()
    assert isinstance(projects, list)
    assert len(projects) > 0
    assert "id" in projects[0]
    assert projects[0]["name"] == "UAV"

    # 2. Simulation stack health
    health = manage_simulation_stack(action="status")
    assert "containers" in health
    assert "skytrack-deamon-gcs-backend-1" in health["containers"]

    # 3. Flight Report harvesting
    report = harvest_flight_report(save_to_disk=False)
    assert "report" in report
    assert "markdown_report" in report
    assert "Autonomous Flight Report" in report["markdown_report"]

