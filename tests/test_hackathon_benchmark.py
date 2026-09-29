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
    # Default scoring fails closed on synthetic reports
    score_default = score_hackathon_mission_report(Path(sim_res["report_path"]))
    assert score_default["total_score"] == 0.0
    assert score_default["details"]["provenance"] == "synthetic"

    # Explicit allow_synthetic evaluates the kinematic simulation
    score_100 = score_hackathon_mission_report(Path(sim_res["report_path"]), allow_synthetic=True)
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
    score_broken = score_hackathon_mission_report(Path(sim_res_broken["report_path"]), allow_synthetic=True)
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
    # Fail-closed default
    score_default = score_hackathon_mission_report(Path(sim_res["report_path"]))
    assert score_default["total_score"] == 0.0
    assert score_default["details"]["provenance"] == "synthetic"

    # Explicit allow_synthetic evaluates kinematic simulation
    score = score_hackathon_mission_report(Path(sim_res["report_path"]), allow_synthetic=True)
    assert score["total_score"] == 100.0


def test_rubric_penalizes_missing_waypoint_reached_events(tmp_path: Path) -> None:
    """Verify that removing WAYPOINT_REACHED events drops valid_route and true_patrol_metrics to 0.0."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Strip all WAYPOINT_REACHED events
    filtered_events = [
        e for e in data["execution_report"][0]["execution_events"]
        if e.get("event") != "WAYPOINT_REACHED"
    ]
    data["execution_report"][0]["execution_events"] = filtered_events
    no_wps_file = tmp_path / "no_reached_wps.json"
    no_wps_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(no_wps_file)
    assert result["rubric_scores"]["valid_route"] == 0.0
    assert result["rubric_scores"]["true_patrol_metrics"] == 0.0
    assert result["total_score"] <= 70.0


def test_rubric_penalizes_missing_rtl_event(tmp_path: Path) -> None:
    """Verify that omitting RTL events zeroes out rtl_completion despite final_status == 'Succeeded'."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Strip all RTL events from execution_events
    filtered_events = [
        e for e in data["execution_report"][0]["execution_events"]
        if e.get("event") != "RTL"
    ]
    data["execution_report"][0]["execution_events"] = filtered_events
    no_rtl_file = tmp_path / "no_rtl.json"
    no_rtl_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(no_rtl_file)
    assert result["rubric_scores"]["rtl_completion"] == 0.0
    assert result["total_score"] == 88.0


def test_rubric_penalizes_non_urban_world(tmp_path: Path) -> None:
    """Verify that running in 'warehouse' or any non-urban world zeroes out mission_success and valid_route."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    data["execution_metadata"]["world"] = "warehouse"
    if "world" in data["execution_report"][0].get("status_summary", {}):
        data["execution_report"][0]["status_summary"]["world"] = "warehouse"

    bad_world_file = tmp_path / "bad_world.json"
    bad_world_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_world_file)
    assert result["rubric_scores"]["mission_success"] == 0.0
    assert result["rubric_scores"]["valid_route"] == 0.0
    assert result["total_score"] == 0.0


def test_rubric_penalizes_altitude_at_34_9m(tmp_path: Path) -> None:
    """Verify that waypoint altitude at 34.9m strictly fails valid_route (threshold >= 35.0m)."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    for w in data["execution_report"][0]["status_summary"]["waypoints_defined"]:
        w["z"] = 34.9
    for e in data["execution_report"][0]["execution_events"]:
        if e.get("event") == "WAYPOINT_REACHED":
            e["data"]["z"] = 34.9

    bad_alt_file = tmp_path / "bad_alt_34_9.json"
    bad_alt_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_alt_file)
    assert result["rubric_scores"]["valid_route"] == 0.0


def test_rubric_penalizes_altitude_at_34_999m(tmp_path: Path) -> None:
    """Verify that 1mm altitude violation (34.999m) is strictly rejected by threshold (>= 35.0 - 1e-6)."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    for w in data["execution_report"][0]["status_summary"]["waypoints_defined"]:
        w["z"] = 34.999
    for e in data["execution_report"][0]["execution_events"]:
        if e.get("event") == "WAYPOINT_REACHED":
            e["data"]["z"] = 34.999

    bad_alt_file = tmp_path / "bad_alt_34_999.json"
    bad_alt_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(bad_alt_file)
    assert result["rubric_scores"]["valid_route"] == 0.0


def test_rubric_penalizes_missing_ball_drop_event(tmp_path: Path) -> None:
    """Verify that removing BALL_DROP zeroes out ball_drop_accuracy and video_recording_wrapped."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    filtered_events = [
        e for e in data["execution_report"][0]["execution_events"]
        if e.get("event") != "BALL_DROP"
    ]
    data["execution_report"][0]["execution_events"] = filtered_events

    no_drop_file = tmp_path / "no_drop.json"
    no_drop_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(no_drop_file)
    assert result["rubric_scores"]["ball_drop_accuracy"] == 0.0
    assert result["rubric_scores"]["video_recording_wrapped"] == 0.0


def test_report_parser_distinguishes_synthetic_vs_authentic(tmp_path: Path) -> None:
    """Verify that parser find_authentic_report_file rejects synthetic simulations."""
    from skytrack_mcp.clients.storage_sync import write_visual_route
    from skytrack_mcp.report.parser import find_authentic_report_file, harvest_mission_report_data
    from skytrack_mcp.simulation.runner import simulate_mission_to_execution_report

    prj_id = "PRJ_SYNTH"
    mis_id = "MIS_SYNTH"
    mis_dir = tmp_path / f"prj-{prj_id}" / f"mis-{mis_id}"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text('{"world": "urban", "vehicle": "x500_tennis_balls"}', encoding="utf-8")
    (mis_dir / "plan.json").write_text('{"spawnLocation": [0,0,0], "sequences": []}', encoding="utf-8")

    sim_res = simulate_mission_to_execution_report(
        mission_id=mis_id,
        project_id=prj_id,
        client_data_dir=tmp_path,
        save_to_disk=True,
    )
    assert "synthetic-mission-report.json" in sim_res["report_path"]

    # find_authentic_report_file must NOT return synthetic report
    authentic_found = find_authentic_report_file(mis_dir)
    assert authentic_found is None

    # harvest_mission_report_data must state report_provenance == "synthetic_only"
    harvested = harvest_mission_report_data(mis_id, prj_id, client_data_dir=tmp_path)
    assert harvested["report_provenance"] == "synthetic_only"
    assert harvested["authentic_report_file"] is None
    assert harvested["synthetic_report_file"] == "synthetic-mission-report.json"
    assert harvested["execution_status"] == "UNKNOWN"


def test_rubric_penalizes_repeated_same_waypoint_reached_spam(tmp_path: Path) -> None:
    """Verify that 7 WAYPOINT_REACHED events repeating only WP 0 fail valid_route and true_patrol_metrics."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    wp0 = data["execution_report"][0]["status_summary"]["waypoints_defined"][0]
    for e in data["execution_report"][0]["execution_events"]:
        if e.get("event") == "WAYPOINT_REACHED":
            e["data"]["x"] = wp0["x"]
            e["data"]["y"] = wp0["y"]
            e["data"]["z"] = wp0["z"]
            e["data"]["wp_index"] = 0

    spam_file = tmp_path / "spam_wp0.json"
    spam_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(spam_file)
    assert result["rubric_scores"]["valid_route"] == 0.0
    assert result["rubric_scores"]["true_patrol_metrics"] == 0.0


def test_rubric_penalizes_world_frame_ball_drop_spoofing(tmp_path: Path) -> None:
    """Verify that BALL_DROP coordinates in world frame (-83.74, -28.18) do NOT pass local-frame check."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    for e in data["execution_report"][0]["execution_events"]:
        if e.get("event") == "BALL_DROP":
            e["data"]["x"] = FIRE_POINT_WORLD[0]
            e["data"]["y"] = FIRE_POINT_WORLD[1]

    spoof_file = tmp_path / "world_frame_drop.json"
    spoof_file.write_text(json.dumps(data), encoding="utf-8")

    result = score_hackathon_mission_report(spoof_file)
    assert result["rubric_scores"]["ball_drop_accuracy"] == 0.0


def test_submission_dossier_marks_missing_fields_as_unknown() -> None:
    """Verify that missing submission dossier fields return 'UNKNOWN' rather than conflating flight duration."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    result = score_hackathon_mission_report(sample_path)
    dossier = result["details"]["submission_dossier"]
    assert dossier["report_url_public"] == "UNKNOWN"
    assert dossier["video_duration_le_90s"] == "UNKNOWN"
    assert dossier["team_information_included"] == "UNKNOWN"


def test_rubric_rejects_mismatched_mission_or_execution_id() -> None:
    """Verify that expected_mission_id and expected_execution_id fail closed when mismatched or empty."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")

    # Wrong mission_id must score 0.0
    res_wrong_mis = score_hackathon_mission_report(
        sample_path,
        expected_mission_id="WRONG_MISSION_ID",
    )
    assert res_wrong_mis["total_score"] == 0.0

    # Wrong execution_id must score 0.0
    res_wrong_exec = score_hackathon_mission_report(
        sample_path,
        expected_execution_id="wrong-exec-uuid",
    )
    assert res_wrong_exec["total_score"] == 0.0

    # Empty execution_id when required must score 0.0
    res_empty_exec = score_hackathon_mission_report(
        sample_path,
        expected_execution_id="",
    )
    assert res_empty_exec["total_score"] == 0.0

    # Matching mission_id and execution_id scores 100.0
    res_match = score_hackathon_mission_report(
        sample_path,
        expected_mission_id="01M1H032A86R5CVX521T9KGT7Z",
        expected_execution_id="08ce5361-8a54-4147-bf06-a78f6f52dec1",
    )
    assert res_match["total_score"] == 100.0


def test_rubric_evaluates_matching_entry_in_multi_entry_report(tmp_path: Path) -> None:
    """Verify that score_hackathon_mission_report selects the entry matching expected_execution_id even if it is not entry 0."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Entry 0: Stale / incomplete run (e.g. failed route)
    stale_entry = json.loads(json.dumps(data["execution_report"][0]))
    stale_entry["execution_id"] = "stale-execution-id-0001"
    stale_entry["status_summary"]["final_status"] = "Failed"
    stale_entry["execution_events"] = []

    # Entry 1: The real winning run
    winning_entry = json.loads(json.dumps(data["execution_report"][0]))
    winning_entry["execution_id"] = "winning-execution-id-0002"

    multi_report_data = {
        "execution_metadata": data["execution_metadata"],
        "execution_report": [stale_entry, winning_entry],
    }

    multi_file = tmp_path / "multi_execution_report.json"
    multi_file.write_text(json.dumps(multi_report_data), encoding="utf-8")

    # When expected_execution_id points to winning_entry, it must score 100.0 rather than reading stale entry 0
    res = score_hackathon_mission_report(
        multi_file,
        expected_execution_id="winning-execution-id-0002",
    )
    assert res["total_score"] == 100.0
    assert res["rubric_scores"]["mission_success"] == 22.0

    # When expected_execution_id is omitted, it should default to the latest entry (winning_entry)
    res_default = score_hackathon_mission_report(multi_file)
    assert res_default["total_score"] == 100.0



@pytest.mark.asyncio
async def test_dry_run_hackathon_runner_is_side_effect_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_hackathon_urban_fire_mission(run_live=False) runs in an isolated tmp workspace without Cloud sync, UI focus, or hardcoded mission_id mutation."""
    import evals.run_hackathon_mission as rhm

    called_forbidden = []
    monkeypatch.setattr(rhm, "sync_mission_to_cloud", lambda *a, **kw: called_forbidden.append("sync_mission_to_cloud"))
    monkeypatch.setattr(rhm, "tool_skytrack_focus", lambda *a, **kw: called_forbidden.append("tool_skytrack_focus"))
    monkeypatch.setattr(rhm, "execute_route_mission", lambda *a, **kw: called_forbidden.append("execute_route_mission"))
    monkeypatch.setattr(rhm, "REPORT_OUTPUT", tmp_path / "dry_run_eval.json")

    out = await rhm.run_hackathon_urban_fire_mission(run_live=False)
    assert called_forbidden == []
    assert out["mission_id"] == "DRYRUN_URBAN_FIRE"
    assert out["comparison_verdict"]["live_mission_verified"] is False
    assert out["comparison_verdict"]["kinematic_dry_run_100_points"] is True


@pytest.mark.asyncio
async def test_live_runner_fails_explicitly_if_cloud_create_mission_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_hackathon_urban_fire_mission(run_live=True) stops with explicit error instead of inventing LIVE_<uuid> when Cloud creation fails."""
    import evals.run_hackathon_mission as rhm
    from skytrack_mcp.mcp import tools as mcp_tools

    async def fake_ctx():
        return {
            "active_project_id": "PRJ_TEST",
            "selected_world": "urban",
            "selected_vehicle": "x500_tennis_balls",
        }

    def fail_create(*a, **kw):
        raise RuntimeError("Cloud API unreachable")

    draw_called = []
    monkeypatch.setattr(rhm, "tool_skytrack_get_context", fake_ctx)
    monkeypatch.setattr(mcp_tools, "tool_skytrack_create_mission", fail_create)
    monkeypatch.setattr(rhm, "draw_route_on_map", lambda *a, **kw: draw_called.append(True))

    with pytest.raises(RuntimeError, match="Failed to create fresh mission"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True)

    assert draw_called == []


@pytest.mark.asyncio
async def test_live_runner_refuses_dispatch_if_telemetry_disconnected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_hackathon_urban_fire_mission(run_live=True) gates preflight telemetry (connected=True) before dispatching."""
    import evals.run_hackathon_mission as rhm
    from skytrack_mcp.clients import docker_exec, storage_sync

    async def fake_ctx():
        return {
            "active_project_id": "PRJ_TEST",
            "selected_world": "urban",
            "selected_vehicle": "x500_tennis_balls",
        }

    monkeypatch.setattr(rhm, "tool_skytrack_get_context", fake_ctx)
    monkeypatch.setattr(rhm, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(rhm, "sync_mission_to_cloud", lambda **kw: {"synced_mission_id": kw["mission_id"]})
    monkeypatch.setattr(rhm, "tool_skytrack_focus", lambda: {})
    monkeypatch.setattr(rhm, "tool_ui_snapshot", lambda **kw: {})
    monkeypatch.setattr(docker_exec, "fetch_live_mavlink_telemetry", lambda: {"connected": False, "error": "no heartbeat"})

    dispatch_called = []

    async def fake_dispatch(**kw):
        dispatch_called.append(True)
        return {"status_code": 200, "response": {}}

    monkeypatch.setattr(rhm, "execute_route_mission", fake_dispatch)

    with pytest.raises(RuntimeError, match="Preflight check failed"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_EXPLICIT")

    assert dispatch_called == []


def test_rubric_penalizes_interrupted_video_recording_wrapping_drop(tmp_path: Path) -> None:
    """Verify that video recording interrupted before drop (START, STOP, DROP, START, STOP) scores 0.0."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Replace events with an interrupted recording pattern
    # Event 0: START
    # Event 1: STOP
    # Event 2: DROP
    # Event 3: START
    # Event 4: STOP
    interrupted_events = [
        {"event": "RECORDING_STARTED", "data": {"status": "Recording started"}},
        {"event": "RECORDING_STOPPED", "data": {"status": "Recording stopped"}},
        {"event": "BALL_DROP", "data": {"x": -287.424, "y": 125.517, "z": 35.0}},
        {"event": "RECORDING_STARTED", "data": {"status": "Recording started"}},
        {"event": "RECORDING_STOPPED", "data": {"status": "Recording stopped"}},
    ]
    data["execution_report"][0]["execution_events"] = interrupted_events
    test_file = tmp_path / "interrupted_video.json"
    test_file.write_text(json.dumps(data), encoding="utf-8")

    res = score_hackathon_mission_report(test_file)
    assert res["rubric_scores"]["video_recording_wrapped"] == 0.0


def test_submission_dossier_handles_none_or_string_duration_safely(tmp_path: Path) -> None:
    """Verify that float(video_duration) does not crash on string/null/unknown metadata."""
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    data = json.loads(sample_path.read_text(encoding="utf-8"))

    # Test with string "unknown"
    data["execution_metadata"]["submission_video_duration_s"] = "unknown"
    res1 = score_hackathon_mission_report(sample_path)  # baseline
    test_file = tmp_path / "str_duration.json"
    test_file.write_text(json.dumps(data), encoding="utf-8")
    res_str = score_hackathon_mission_report(test_file)
    assert res_str["details"]["submission_dossier"]["video_duration_le_90s"] == "UNKNOWN"

    # Test with None
    data["execution_metadata"]["submission_video_duration_s"] = None
    test_file2 = tmp_path / "none_duration.json"
    test_file2.write_text(json.dumps(data), encoding="utf-8")
    res_none = score_hackathon_mission_report(test_file2)
    assert res_none["details"]["submission_dossier"]["video_duration_le_90s"] == "UNKNOWN"

    # Test with valid float 85.0
    data["execution_metadata"]["submission_video_duration_s"] = 85.0
    test_file3 = tmp_path / "valid_duration.json"
    test_file3.write_text(json.dumps(data), encoding="utf-8")
    res_valid = score_hackathon_mission_report(test_file3)
    assert res_valid["details"]["submission_dossier"]["video_duration_le_90s"] is True


@pytest.mark.asyncio
async def test_live_runner_preflight_checks_armed_landed_state_and_battery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify live runner gates is_armed=False, landed_state in ('ON_GROUND', 'LANDED'), and battery >= 20%."""
    import evals.run_hackathon_mission as rhm
    from skytrack_mcp.clients import docker_exec, storage_sync

    async def fake_ctx():
        return {
            "active_project_id": "PRJ_TEST",
            "selected_world": "urban",
            "selected_vehicle": "x500_tennis_balls",
        }

    monkeypatch.setattr(rhm, "tool_skytrack_get_context", fake_ctx)
    monkeypatch.setattr(rhm, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(rhm, "sync_mission_to_cloud", lambda **kw: {"synced_mission_id": kw["mission_id"]})
    monkeypatch.setattr(rhm, "tool_skytrack_focus", lambda: {})
    monkeypatch.setattr(rhm, "tool_ui_snapshot", lambda **kw: {})
    async def fake_exec(**kw):
        return {"status_code": 200, "response": {}}

    monkeypatch.setattr(rhm, "execute_route_mission", fake_exec)

    # Case 1: is_armed is True -> refuse dispatch
    monkeypatch.setattr(
        docker_exec,
        "fetch_live_mavlink_telemetry",
        lambda: {"connected": True, "is_armed": True, "landed_state": "ON_GROUND", "battery_percentage": 90.0},
    )
    with pytest.raises(RuntimeError, match="already armed"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_EXPLICIT")

    # Case 2: landed_state is IN_AIR -> refuse dispatch
    monkeypatch.setattr(
        docker_exec,
        "fetch_live_mavlink_telemetry",
        lambda: {"connected": True, "is_armed": False, "landed_state": "IN_AIR", "battery_percentage": 90.0},
    )
    with pytest.raises(RuntimeError, match="not ON_GROUND"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_EXPLICIT")

    # Case 3: battery_percentage < 20% -> refuse dispatch
    monkeypatch.setattr(
        docker_exec,
        "fetch_live_mavlink_telemetry",
        lambda: {"connected": True, "is_armed": False, "landed_state": "ON_GROUND", "battery_percentage": 15.0},
    )
    with pytest.raises(RuntimeError, match="battery is critically low"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_EXPLICIT")


@pytest.mark.asyncio
async def test_live_runner_refuses_dispatch_if_runtime_world_or_vehicle_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify live runner checks runtime world/vehicle immediately before dispatch and refuses execution on mismatch."""
    import evals.run_hackathon_mission as rhm
    from skytrack_mcp.clients import docker_exec, storage_sync

    async def fake_ctx():
        return {
            "active_project_id": "PRJ_TEST",
            "selected_world": "farm-petersburg",
            "selected_vehicle": "x500_mono_cam",
        }

    dispatch_called = []

    async def fake_exec(**kw):
        dispatch_called.append(True)
        return {"status_code": 200, "response": {}}

    monkeypatch.setattr(rhm, "tool_skytrack_get_context", fake_ctx)
    monkeypatch.setattr(rhm, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(rhm, "sync_mission_to_cloud", lambda **kw: {"synced_mission_id": kw["mission_id"]})
    monkeypatch.setattr(rhm, "tool_skytrack_focus", lambda: {})
    monkeypatch.setattr(rhm, "tool_ui_snapshot", lambda **kw: {})
    monkeypatch.setattr(rhm, "execute_route_mission", fake_exec)
    monkeypatch.setattr(
        docker_exec,
        "fetch_live_mavlink_telemetry",
        lambda: {"connected": True, "is_armed": False, "landed_state": "ON_GROUND", "battery_percentage": 90.0},
    )

    with pytest.raises(RuntimeError, match="runtime simulation world is 'farm-petersburg', expected 'urban'"):
        await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_EXPLICIT")

    assert dispatch_called == []



@pytest.mark.asyncio
async def test_runner_provenance_is_authentic_when_native_report_exists_even_if_score_below_100(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that agent_independent_solution.provenance is 'authentic' when native report exists, regardless of score < 100."""
    monkeypatch.setattr("evals.run_hackathon_mission.REPORT_OUTPUT", tmp_path / "live_eval.json")
    import evals.run_hackathon_mission as rhm
    from skytrack_mcp.clients import docker_exec, storage_sync
    from skytrack_mcp.report import parser as rparser

    async def fake_ctx():
        return {
            "active_project_id": "PRJ_TEST",
            "selected_world": "urban",
            "selected_vehicle": "x500_tennis_balls",
        }

    async def fake_exec(**kw):
        return {"status_code": 200, "response": {"execution_id": "exec-123"}}

    monkeypatch.setattr(rhm, "tool_skytrack_get_context", fake_ctx)
    monkeypatch.setattr(rhm, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setattr(rhm, "sync_mission_to_cloud", lambda **kw: {"synced_mission_id": kw["mission_id"]})
    monkeypatch.setattr(rhm, "tool_skytrack_focus", lambda: {})
    monkeypatch.setattr(rhm, "tool_ui_snapshot", lambda **kw: {})
    monkeypatch.setattr(rhm, "execute_route_mission", fake_exec)
    monkeypatch.setattr(
        docker_exec,
        "fetch_live_mavlink_telemetry",
        lambda: {"connected": True, "is_armed": False, "landed_state": "ON_GROUND", "battery_percentage": 85.0},
    )

    # Provide a native report that fails some criterion (e.g. score = 82.0)
    native_file = tmp_path / "prj-PRJ_TEST" / "mis-MIS_TEST" / "skytrack-mission-report.json"
    native_file.parent.mkdir(parents=True, exist_ok=True)
    sample_path = Path("evals/fixtures/hackathon-2026/sample-answer-report.json")
    sub_100_data = json.loads(sample_path.read_text(encoding="utf-8"))
    sub_100_data["execution_report"][0]["execution_id"] = "exec-123"
    # Make video fail so total_score = 82.0
    sub_100_data["execution_report"][0]["execution_events"] = [
        e for e in sub_100_data["execution_report"][0]["execution_events"]
        if "Recording" not in str((e.get("data") or {}).get("status", ""))
    ]
    native_file.write_text(json.dumps(sub_100_data), encoding="utf-8")

    monkeypatch.setattr(rparser, "find_authentic_report_file", lambda *a, **kw: native_file)

    out = await rhm.run_hackathon_urban_fire_mission(run_live=True, target_mission_id="MIS_TEST")
    assert out["agent_independent_solution"]["provenance"] == "authentic"
    assert out["comparison_verdict"]["live_mission_verified"] is False


@pytest.mark.asyncio
async def test_runner_collision_check_includes_spawn_departure_and_return_legs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that collision checking covers departure from spawn (climb to 36m) through all waypoints and return to spawn."""
    import evals.run_hackathon_mission as rhm

    checked_routes = []

    def spy_check(world, coords_3d, clearance_m=0.4):
        checked_routes.append(coords_3d)
        return {"world": world, "is_collision_free": False, "geometry_complete": False, "unresolved_models": ["model://urban"], "conflicts": []}

    monkeypatch.setattr(rhm, "check_route_collisions", spy_check)
    monkeypatch.setattr(rhm, "REPORT_OUTPUT", tmp_path / "check_eval.json")

    await rhm.run_hackathon_urban_fire_mission(run_live=False)

    assert len(checked_routes) == 1
    route = checked_routes[0]
    # Route must start at spawn position at 36m altitude, cover waypoints, and return to spawn at 36m
    assert route[0] == [rhm.SPAWN_POINT_WORLD[0], rhm.SPAWN_POINT_WORLD[1], 36.0]
    assert route[-1] == [rhm.SPAWN_POINT_WORLD[0], rhm.SPAWN_POINT_WORLD[1], 36.0]
    assert len(route) == 8  # 1 departure + 6 waypoints + 1 return
