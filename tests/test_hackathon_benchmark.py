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
