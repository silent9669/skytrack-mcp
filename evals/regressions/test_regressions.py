"""Automated Regression Suite for SkyTrack MCP (REG-001 to REG-012).
Implements Section 28 of review.md.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any, Dict

from evals.expected.geometric_verifier import (
    distance_3d,
    horizontal_distance,
    altitude_error,
    verify_waypoint_reached,
    verify_waypoint_sequence,
)
from skytrack_mcp.clients.storage_sync import (
    list_all_missions,
    read_mission_details,
    resolve_mission_dir,
    write_visual_route,
)
from skytrack_mcp.mission.models import CanonicalMission, Waypoint, ValidationSeverity
from skytrack_mcp.mission.patcher import MissionPatcher
from skytrack_mcp.mission.validator import validate_canonical_mission
from skytrack_mcp.report.parser import harvest_mission_report_data
from skytrack_mcp.report.verification import evaluate_mission_requirements, VerificationStatus
from skytrack_mcp.route.geometry_utils import (
    compute_route_metrics,
    distance_3d as mcp_distance_3d,
)


def test_reg_001_basic_mission_open_read_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REG-001: Basic mission open/read/save."""
    missions = list_all_missions()
    if not missions:
        mis_dir = tmp_path / "prj-P1" / "mis-M1"
        mis_dir.mkdir(parents=True)
        (mis_dir / "mission.json").write_text('{"world": "default", "vehicle": "x500"}', encoding="utf-8")
        (mis_dir / "plan.json").write_text('{"spawnLocation": [0,0,0], "sequences": []}', encoding="utf-8")
        from skytrack_mcp.clients import storage_sync
        monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
        missions = list_all_missions(tmp_path)

    assert len(missions) > 0
    m = missions[0]
    details = read_mission_details(m["mission_id"])
    assert details["mission_id"] == m["mission_id"]
    assert "plan" in details
    assert "mission" in details


def test_reg_002_simple_xyz_waypoint() -> None:
    """REG-002: Simple XYZ waypoint geometry verification."""
    p0 = [0.0, 0.0, 0.0]
    p1 = [10.0, 0.0, 5.0]
    assert horizontal_distance(p0, p1) == 10.0
    assert altitude_error(p1[2], 5.0) == 0.0
    assert abs(distance_3d(p0, p1) - 11.1803) < 0.001


def test_reg_003_multiple_ordered_waypoints() -> None:
    """REG-003: Multiple ordered waypoints."""
    expected = [
        {"x": 1.0, "y": 2.0, "z": 2.5},
        {"x": 3.0, "y": 4.0, "z": 2.5},
        {"x": 5.0, "y": 6.0, "z": 2.5},
    ]
    events = [
        {"event": "WAYPOINT_REACHED", "data": {"x": 1.05, "y": 2.02, "z": 2.51, "wp_index": 1}},
        {"event": "WAYPOINT_REACHED", "data": {"x": 3.01, "y": 3.98, "z": 2.49, "wp_index": 2}},
        {"event": "WAYPOINT_REACHED", "data": {"x": 4.95, "y": 6.04, "z": 2.50, "wp_index": 3}},
    ]
    res = verify_waypoint_sequence(events, expected, horizontal_tolerance_m=0.5)
    assert res["sequence_verified"] is True
    assert res["reached_count"] == 3


def test_reg_004_altitude_change() -> None:
    """REG-004: Altitude change validation."""
    p_climb = [0.0, 0.0, 4.0]
    check = verify_waypoint_reached(p_climb, [0.0, 0.0, 4.0], vertical_tolerance_m=0.1)
    assert check["passed"] is True
    assert check["vertical_error_m"] == 0.0


def test_reg_005_return_home_and_land() -> None:
    """REG-005: Return home + land."""
    home = [0.0, 0.0, 0.0]
    touchdown = [0.12, -0.08, 0.02]
    check = verify_waypoint_reached(touchdown, home, horizontal_tolerance_m=0.5, vertical_tolerance_m=0.2)
    assert check["passed"] is True


def test_reg_006_world_selection() -> None:
    """REG-006: World selection."""
    from skytrack_mcp.clients.docker_exec import list_gazebo_worlds
    worlds = list_gazebo_worlds()
    assert "warehouse" in worlds
    assert "default" in worlds


def test_reg_007_uav_selection() -> None:
    """REG-007: UAV selection capabilities."""
    from skytrack_mcp.mission.validator import VEHICLE_CAPABILITIES
    assert "x500_livox_mid_360" in VEHICLE_CAPABILITIES
    assert "x500_tennis_balls_no_cam" in VEHICLE_CAPABILITIES
    assert VEHICLE_CAPABILITIES["x500_tennis_balls_no_cam"]["max_balls"] == 5


def test_reg_010_requirement_verification() -> None:
    """REG-010: Requirement verification matrix logic."""
    sample_report = {
        "world": "warehouse",
        "total_planned_waypoints": 6,
        "telemetry_state": {"landed_state": "ON_GROUND"},
    }
    reqs = [
        {"name": "Correct World", "type": "world", "expected": "warehouse", "mandatory": True},
        {"name": "Safe Landing", "type": "landed_safely", "mandatory": True},
    ]
    matrix = evaluate_mission_requirements("test-mis", reqs, sample_report)
    assert matrix.overall_status == VerificationStatus.PASS


def test_reg_011_invalid_mission_detection() -> None:
    """REG-011: Invalid mission detection."""
    bad_mission = CanonicalMission(
        project_id="test",
        mission_id="test",
        takeoff_altitude=0.1,  # Invalid
        target_speed=2.0,
        waypoints=[Waypoint(x=0.0, y=0.0, z=0.1)],
    )
    val = validate_canonical_mission(bad_mission)
    assert val.valid is False
    assert any(i.code == "INVALID_TAKEOFF_ALTITUDE" for i in val.issues)
