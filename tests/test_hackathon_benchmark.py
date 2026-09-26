"""Tests for the Hackathon 2026 Urban Fire Rescue evaluation engine.
Verifies the reference solution achieves 100 points and verifies strict penalties for constraint violations.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from evals.expected.hackathon_evaluator import (
    FLIGHT_AREA_POLYGON,
    FIRE_POINT_WORLD,
    point_in_polygon,
    score_hackathon_mission_report,
)


def test_point_in_polygon_containment() -> None:
    """Verify point_in_polygon algorithm against known inside/outside coordinates."""
    # Centroid of polygon: roughly (80, -90)
    assert point_in_polygon((80.0, -90.0), FLIGHT_AREA_POLYGON) is True
    # Fire point: (-83.74, -28.18)
    assert point_in_polygon(FIRE_POINT_WORLD, FLIGHT_AREA_POLYGON) is True
    # Spawn point: (203.684, -153.697)
    assert point_in_polygon((203.684, -153.697), FLIGHT_AREA_POLYGON) is True

    # Far outside points
    assert point_in_polygon((500.0, 500.0), FLIGHT_AREA_POLYGON) is False
    assert point_in_polygon((-200.0, -300.0), FLIGHT_AREA_POLYGON) is False
    assert point_in_polygon((0.0, 200.0), FLIGHT_AREA_POLYGON) is False


def test_reference_solution_scores_100_points() -> None:
    """Verify that the official ground-truth sample answer scores 100/100 points."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    assert sample_path.exists()

    result = score_hackathon_mission_report(sample_path)
    assert result["total_score"] == 100.0
    assert result["passed_threshold"] is True
    assert result["rubric_scores"]["mission_success"] == 22.0
    assert result["rubric_scores"]["valid_route"] == 15.0
    assert result["rubric_scores"]["true_patrol_metrics"] == 15.0
    assert result["rubric_scores"]["video_recording_wrapped"] == 18.0
    assert result["rubric_scores"]["ball_drop_accuracy"] == 18.0
    assert result["rubric_scores"]["rtl_completion"] == 12.0


def test_rubric_penalizes_outside_polygon(tmp_path: Path) -> None:
    """Verify that waypoints outside the flight polygon zero out the valid_route criterion."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Push waypoint 2 far outside
    data["execution_report"][0]["status_summary"]["waypoints_defined"][2]["x"] = 500.0
    bad_file = tmp_path / "bad_polygon.json"
    bad_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_file)
    assert result["rubric_scores"]["valid_route"] == 0.0
    assert result["total_score"] == 85.0


def test_rubric_penalizes_altitude_below_35m(tmp_path: Path) -> None:
    """Verify that waypoint altitude below 35m zeroes out valid_route criterion."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Lower altitude to 20m (below 35m minimum)
    for w in data["execution_report"][0]["status_summary"]["waypoints_defined"]:
        w["z"] = 20.0
    bad_file = tmp_path / "bad_alt.json"
    bad_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_file)
    assert result["rubric_scores"]["valid_route"] == 0.0


def test_rubric_penalizes_missed_fire_point(tmp_path: Path) -> None:
    """Verify that ball drop missing the fire point (>3m) zeroes out accuracy score."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Move ball drop 20m away from fire point
    for e in data["execution_report"][0]["execution_events"]:
        if e.get("event") == "BALL_DROP":
            e["data"]["x"] = -200.0
            e["data"]["y"] = 0.0
    bad_file = tmp_path / "bad_drop.json"
    bad_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_file)
    assert result["rubric_scores"]["ball_drop_accuracy"] == 0.0
    assert result["total_score"] == 82.0


def test_rubric_penalizes_missing_video_recording(tmp_path: Path) -> None:
    """Verify that missing or misordered video recording zeroes out video_recording_wrapped (18 pts)."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Remove Recording started / Recording stopped statuses from execution_events
    filtered_events = []
    for e in data["execution_report"][0]["execution_events"]:
        status = str((e.get("data") or {}).get("status", "")).lower()
        if "recording started" in status or "recording stopped" in status:
            continue
        if e.get("event") in ("RECORDING_STARTED", "RECORDING_STOPPED"):
            continue
        filtered_events.append(e)
    data["execution_report"][0]["execution_events"] = filtered_events

    no_video_file = tmp_path / "no_video.json"
    no_video_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(no_video_file)
    assert result["rubric_scores"]["video_recording_wrapped"] == 0.0
    assert result["total_score"] == 82.0


def test_dynamic_simulation_from_authored_mission(tmp_path: Path) -> None:
    """Verify simulate_mission_to_execution_report dynamically reflects plan.json actions."""
    from skytrack_mcp.clients.storage_sync import write_visual_route
    from skytrack_mcp.simulation.runner import simulate_mission_to_execution_report

    prj_id = "TESTHACK"
    mis_id = "MISHACK1"
    mis_dir = tmp_path / f"prj-{prj_id}" / f"mis-{mis_id}"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text('{"world": "urban", "vehicle": "x500_tennis_balls"}', encoding="utf-8")
    (mis_dir / "plan.json").write_text('{"spawnLocation": [203.684, -153.697, 0.452], "sequences": []}', encoding="utf-8")

    waypoints = [
        {"x": 197.354, "y": -150.771, "z": 35.0},
        {"x": 141.762, "y": -109.024, "z": 35.0},
        {"x": 84.974,  "y": -110.328, "z": 35.0},
        {"x": 4.517,   "y": -45.804,  "z": 35.0, "after_action": "start-recording-video"},
        {"x": -83.74,  "y": -28.18,   "z": 35.0, "after_action": "drop-ball"},
        {"x": 46.045,  "y": -141.705, "z": 35.0, "after_action": "stop-recording-video"},
        {"x": 203.684, "y": -153.697, "z": 35.0},
    ]
    write_visual_route(
        waypoints=waypoints,
        mission_id=mis_id,
        spawn_location=[203.684, -153.697, 0.452],
        takeoff_altitude=35.0,
        target_speed=2.5,
        end_action="rtl",
        world="urban",
        vehicle="x500_tennis_balls",
        client_data_dir=tmp_path,
    )

    sim_res = simulate_mission_to_execution_report(
        mission_id=mis_id,
        project_id=prj_id,
        client_data_dir=tmp_path,
        save_to_disk=True,
    )
    score_100 = score_hackathon_mission_report(Path(sim_res["report_path"]))
    assert score_100["total_score"] == 100.0

    # Now mutate plan.json to omit start-recording-video and verify simulated report drops to 82.0
    waypoints_no_rec = [
        {"x": 197.354, "y": -150.771, "z": 35.0},
        {"x": 141.762, "y": -109.024, "z": 35.0},
        {"x": 84.974,  "y": -110.328, "z": 35.0},
        {"x": 4.517,   "y": -45.804,  "z": 35.0},  # Missing start-recording-video!
        {"x": -83.74,  "y": -28.18,   "z": 35.0, "after_action": "drop-ball"},
        {"x": 46.045,  "y": -141.705, "z": 35.0, "after_action": "stop-recording-video"},
        {"x": 203.684, "y": -153.697, "z": 35.0},
    ]
    write_visual_route(
        waypoints=waypoints_no_rec,
        mission_id=mis_id,
        spawn_location=[203.684, -153.697, 0.452],
        takeoff_altitude=35.0,
        target_speed=2.5,
        end_action="rtl",
        world="urban",
        vehicle="x500_tennis_balls",
        client_data_dir=tmp_path,
    )
    sim_res_broken = simulate_mission_to_execution_report(
        mission_id=mis_id,
        project_id=prj_id,
        client_data_dir=tmp_path,
        save_to_disk=True,
    )
    score_broken = score_hackathon_mission_report(Path(sim_res_broken["report_path"]))
    assert score_broken["rubric_scores"]["video_recording_wrapped"] == 0.0
    assert score_broken["total_score"] == 82.0


def test_independent_urban_patrol_route_planner(tmp_path: Path) -> None:
    """Verify generate_independent_urban_patrol_route produces a valid 6-waypoint route scoring 100/100."""
    from evals.run_hackathon_mission import generate_independent_urban_patrol_route
    from skytrack_mcp.clients.cloud_client import build_cloud_commands_v2
    from skytrack_mcp.clients.storage_sync import write_visual_route
    from skytrack_mcp.simulation.runner import simulate_mission_to_execution_report

    route = generate_independent_urban_patrol_route()
    assert len(route) == 6
    assert all(w["z"] == 36.0 for w in route)

    # Verify cloud commands.v2 payload builder
    v2_cmd = build_cloud_commands_v2(
        world="urban",
        vehicle="x500_tennis_balls",
        actions=route,
        spawn_location=[203.684, -153.697, 0.452],
        takeoff_altitude=36.0,
        target_speed=3.0,
    )
    assert v2_cmd["v2"]["metadata"]["world"]["name"] == "urban"
    assert v2_cmd["v2"]["metadata"]["vehicle"]["name"] == "x500_tennis_balls"

    # Verify write_visual_route auto-creates missing mission directory (BUG-0006)
    write_visual_route(
        waypoints=route,
        mission_id="NEW_CLOUD_MIS",
        project_id="NEW_PRJ",
        spawn_location=[203.684, -153.697, 0.452],
        takeoff_altitude=36.0,
        target_speed=3.0,
        world="urban",
        vehicle="x500_tennis_balls",
        client_data_dir=tmp_path,
    )
    sim_res = simulate_mission_to_execution_report(
        mission_id="NEW_CLOUD_MIS",
        project_id="NEW_PRJ",
        client_data_dir=tmp_path,
        save_to_disk=True,
    )
    score = score_hackathon_mission_report(Path(sim_res["report_path"]))
    assert score["total_score"] == 100.0


