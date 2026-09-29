"""Native execution events, not final status or live idle state, prove touchdown."""

import json
from pathlib import Path

from skytrack_mcp.report.parser import find_authentic_report_file, harvest_mission_report_data, render_markdown_flight_report


SAMPLE = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "hackathon-2026" / "sample-answer-report.json"


def test_synthetic_only_summary_is_not_labeled_official():
    report = {
        "report_id": "R1", "timestamp": "2026-09-26", "mission_id": "M1", "project_id": "P1",
        "world": "urban", "vehicle": "x500_tennis_balls", "report_provenance": "synthetic_only",
        "execution_status": "UNKNOWN", "execution_duration_s": 0, "target_speed_m_s": 2,
        "total_planned_waypoints": 6, "total_planned_actions": 9, "takeoff_altitude_m": 36,
    }
    rendered = render_markdown_flight_report(report)
    assert "Official Flight Execution Report" not in rendered
    assert "synthetic_only" in rendered


def test_report_does_not_use_target_speed_as_average_ground_speed():
    report = {
        "report_id": "R1", "timestamp": "2026-09-26", "mission_id": "M1", "project_id": "P1",
        "world": "urban", "vehicle": "x500_tennis_balls", "report_provenance": "authentic",
        "execution_status": "COMPLETED", "execution_duration_s": 10,
        "average_ground_speed_m_s": None, "target_speed_m_s": 5,
        "total_planned_waypoints": 1, "total_planned_actions": 0, "takeoff_altitude_m": 2.5,
    }

    rendered = render_markdown_flight_report(report)

    assert "- **Average Ground Speed:** None m/s" in rendered


def test_derived_flight_report_is_not_a_native_execution_report(tmp_path):
    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "flight_report.json").write_text(json.dumps({
        "mission_id": "M1", "execution_status": "Succeeded",
        "waypoints_reached_count": 6, "report_provenance": "authentic",
    }))
    assert find_authentic_report_file(mission) is None


def test_harvest_selects_matching_execution_within_native_report(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    raw = json.loads(SAMPLE.read_text())
    raw["execution_metadata"]["mission_id"] = "M1"
    old = raw["execution_report"][0]
    old["execution_id"] = "OLD"
    newer = json.loads(json.dumps(old))
    newer["execution_id"] = "NEW"
    newer["status_summary"]["final_status"] = "Failed"
    newer["execution_events"] = []
    raw["execution_report"] = [old, newer]
    (mission / "skytrack-mission-report.json").write_text(json.dumps(raw))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path, execution_id="NEW")
    assert result["report_provenance"] == "authentic"
    assert result["execution_status"] == "Failed"
    assert result["waypoints_reached_count"] == 0
    latest = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)
    assert latest["execution_status"] == "Failed"


def test_harvest_filters_report_by_execution_id(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    old = json.loads(SAMPLE.read_text())
    old["execution_metadata"]["mission_id"] = "M1"
    old["execution_report"][0]["execution_id"] = "OLD"
    (mission / "skytrack-mission-report.json").write_text(json.dumps(old))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path, execution_id="NEW")
    assert result["report_provenance"] == "none"
    assert result["execution_status"] == "UNKNOWN"


def test_report_read_filters_stale_execution(tmp_path, monkeypatch):
    from skytrack_mcp.mcp import tools
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    old = json.loads(SAMPLE.read_text())
    old["execution_metadata"]["mission_id"] = "M1"
    old["execution_report"][0]["execution_id"] = "OLD"
    (mission / "skytrack-mission-report.json").write_text(json.dumps(old))
    monkeypatch.setattr(tools, "resolve_mission_dir", lambda _: (mission, "P1", "M1"))
    monkeypatch.setattr(tools, "harvest_mission_report_data", lambda mid, pid, **kw: parser.harvest_mission_report_data(mid, pid, client_data_dir=tmp_path, **kw))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = tools.tool_skytrack_report_read(mission_id="M1", execution_id="NEW")
    assert result["report"]["report_provenance"] == "none"
    assert result["report"]["execution_status"] == "UNKNOWN"


def test_requirements_tool_filters_stale_execution(tmp_path, monkeypatch):
    from skytrack_mcp.mcp import tools
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    old = json.loads(SAMPLE.read_text())
    old["execution_metadata"]["mission_id"] = "M1"
    old["execution_report"][0]["execution_id"] = "OLD"
    (mission / "skytrack-mission-report.json").write_text(json.dumps(old))
    monkeypatch.setattr(tools, "resolve_mission_dir", lambda _: (mission, "P1", "M1"))
    monkeypatch.setattr(tools, "harvest_mission_report_data", lambda mid, pid, **kw: parser.harvest_mission_report_data(mid, pid, client_data_dir=tmp_path, **kw))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    requirements = [{"name": "Arrivals", "type": "min_waypoints", "expected": 5}]
    result = tools.tool_skytrack_verify_mission_requirements(requirements, mission_id="M1", execution_id="NEW")
    assert result["overall_status"] != "PASS"


def test_harvest_rejects_report_from_another_mission(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    (mission / "skytrack-mission-report.json").write_bytes(SAMPLE.read_bytes())
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)
    assert result["report_provenance"] == "none"
    assert result["execution_status"] == "UNKNOWN"


def test_harvest_uses_native_world_instead_of_planned_world(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    raw = json.loads(SAMPLE.read_text())
    raw["execution_metadata"]["mission_id"] = "M1"
    raw["execution_metadata"]["world"] = "warehouse"
    (mission / "skytrack-mission-report.json").write_text(json.dumps(raw))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)
    assert result["world"] == "warehouse"


def test_harvest_detects_native_completed_return(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500_tennis_balls"}')
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}')
    native = json.loads(SAMPLE.read_text())
    native["execution_metadata"]["mission_id"] = "M1"
    (mission / "skytrack-mission-report.json").write_text(json.dumps(native))
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)
    assert result["report_provenance"] == "authentic"
    assert result["landing_completed"] is True
    assert result["observed_takeoff_altitude_m"] == 35
    assert result["payload_triggers_count"] == 1

    raw = json.loads((mission / "skytrack-mission-report.json").read_text())
    raw["execution_report"][0]["execution_events"] = [
        event for event in raw["execution_report"][0]["execution_events"]
        if event.get("event") != "RTL"
    ]
    (mission / "skytrack-mission-report.json").write_text(json.dumps(raw))
    assert harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)["landing_completed"] is False
