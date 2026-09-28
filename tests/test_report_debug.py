"""Regression coverage for run-scoped, offline flight evidence inspection."""

import json
from pathlib import Path

from skytrack_mcp.report.debug import inspect_mission_run_evidence
from skytrack_mcp.report.parser import harvest_mission_report_data


def _mission_dir(root: Path, project_id: str = "P1", mission_id: str = "M1") -> Path:
    mission = root / f"prj-{project_id}" / f"mis-{mission_id}"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text('{"world":"urban","vehicle":"x500"}', encoding="utf-8")
    (mission / "plan.json").write_text('{"spawnLocation":[0,0,0],"sequences":[]}', encoding="utf-8")
    return mission


def _entry(execution_id: str, timestamp: str, *, provenance: str | None = None) -> dict:
    summary = {
        "final_status": "Succeeded",
        "start_time": timestamp,
        "end_time": timestamp,
        "total_waypoints": 1,
        "waypoints_defined": [{"wp_index": 0, "x": 1, "y": 2, "z": 3}],
    }
    if provenance:
        summary["provenance"] = provenance
    return {
        "execution_id": execution_id,
        "status_summary": summary,
        "execution_events": [
            {"event": "MISSION_END", "timestamp": timestamp, "data": {"phase": "completed"}}
        ],
    }


def test_default_harvest_never_calls_live_docker_and_does_not_invent_battery(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    mission = _mission_dir(tmp_path)
    report = {
        "execution_metadata": {"mission_id": "M1", "status": "Succeeded"},
        "execution_report": [_entry("run-1", "2026-09-27T10:00:00Z")],
    }
    (mission / "skytrack-mission-report.json").write_text(json.dumps(report), encoding="utf-8")

    def fail_if_live(**_kwargs):
        raise AssertionError("default report harvest must not call Docker")

    monkeypatch.setattr(parser, "read_uav_python_logs", fail_if_live)
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", fail_if_live)

    harvested = harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path)

    assert harvested["selected_execution_id"] == "run-1"
    assert harvested["report_provenance"] == "authentic"
    assert harvested["telemetry_state"]["battery_percentage"] is None
    assert harvested["telemetry_state"]["landed_state"] == "UNKNOWN"


def test_inspection_selects_latest_run_and_keeps_media_run_scoped(tmp_path):
    mission = _mission_dir(tmp_path)
    old = _entry("run-old", "2026-09-27T09:00:00Z")
    latest = _entry("run-latest", "2026-09-27T11:00:00Z")
    report = {
        "execution_metadata": {"mission_id": "M1"},
        "execution_report": [latest, old],
    }
    (mission / "skytrack-mission-report.json").write_text(json.dumps(report), encoding="utf-8")
    captures = mission / "media" / "captures"
    recordings = mission / "media" / "recordings"
    captures.mkdir(parents=True)
    recordings.mkdir(parents=True)
    (captures / "run-latest-image.jpg").write_bytes(b"image")
    (captures / "run-old-image.jpg").write_bytes(b"old image")
    (recordings / "run-latest-video.mp4").write_bytes(b"video")
    logs = mission / "logs"
    logs.mkdir()
    (logs / "run-latest.log").write_text(
        "Traceback (most recent call last):\\nValueError: latest run failed\\n", encoding="utf-8"
    )
    (logs / "run-old.log").write_text(
        "Traceback (most recent call last):\\nValueError: old run failed\\n", encoding="utf-8"
    )

    result = inspect_mission_run_evidence("P1", "M1", client_data_dir=tmp_path)

    assert result["selected_execution_id"] == "run-latest"
    assert result["timestamp"] == "2026-09-27T11:00:00Z"
    assert result["report_evidence"] == "NATIVE_CORRELATED"
    assert result["media_inventory"]["captures"] == ["media/captures/run-latest-image.jpg"]
    assert result["media_inventory"]["recordings"] == ["media/recordings/run-latest-video.mp4"]
    assert result["media_inventory"]["unassigned_captures"] == ["media/captures/run-old-image.jpg"]
    traceback_findings = [
        finding for finding in result["diagnostic_findings"] if finding["code"] == "SCRIPT_TRACEBACK"
    ]
    assert len(traceback_findings) == 1
    assert "latest run failed" in traceback_findings[0]["evidence"]
    assert "old run failed" not in traceback_findings[0]["evidence"]


def test_selected_synthetic_execution_is_not_mislabeled_authentic(tmp_path):
    mission = _mission_dir(tmp_path)
    authentic_entry = _entry("run-native", "2026-09-27T09:00:00Z")
    synthetic_entry = _entry("run-synthetic", "2026-09-27T10:00:00Z", provenance="synthetic")
    report = {
        "execution_metadata": {"mission_id": "M1"},
        "execution_report": [authentic_entry, synthetic_entry],
    }
    (mission / "skytrack-mission-report.json").write_text(json.dumps(report), encoding="utf-8")

    harvested = harvest_mission_report_data(
        "M1", "P1", client_data_dir=tmp_path, execution_id="run-synthetic"
    )
    inspected = inspect_mission_run_evidence(
        "P1", "M1", execution_id="run-synthetic", client_data_dir=tmp_path
    )

    assert harvested["report_provenance"] == "synthetic"
    assert harvested["selected_execution_id"] == "run-synthetic"
    assert inspected["report_evidence"] == "SYNTHETIC"
    assert inspected["selected_execution_id"] == "run-synthetic"


def test_user_report_and_logs_produce_execution_scoped_diagnostics(tmp_path):
    _mission_dir(tmp_path)
    user_report = {
        "execution_metadata": {"mission_id": "M1"},
        "execution_report": [
            {
                "execution_id": "user-run-9",
                "status_summary": {
                    "start_time": "2026-09-27T12:00:00Z",
                    "end_time": "2026-09-27T12:01:00Z",
                    "waypoints_defined": [{"wp_index": 0}, {"wp_index": 1}],
                    "battery_percentage": 8,
                },
                "execution_events": [
                    {"event": "WAYPOINT_REACHED", "timestamp": "2026-09-27T12:00:30Z", "data": {"wp_index": 0}},
                    {"event": "ALTITUDE_VIOLATION", "timestamp": "2026-09-27T12:00:45Z", "data": {"altitude_m": 4}},
                ],
            }
        ],
    }
    logs = (
        "Traceback (most recent call last):\n"
        "  File \"mission.py\", line 4, in run\n"
        "ValueError: altitude violation; battery depleted\n"
    )

    result = inspect_mission_run_evidence(
        "P1",
        "M1",
        user_supplied_logs=logs,
        user_supplied_report=user_report,
        client_data_dir=tmp_path,
    )

    codes = {finding["code"] for finding in result["diagnostic_findings"]}
    assert result["report_evidence"] == "USER_PROVIDED"
    assert result["selected_execution_id"] == "user-run-9"
    assert result["timestamp"] == "2026-09-27T12:01:00Z"
    assert {"MISSED_WAYPOINTS", "ALTITUDE_VIOLATION", "BATTERY_DEPLETION", "SCRIPT_TRACEBACK"} <= codes
