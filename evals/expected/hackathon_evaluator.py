"""Hackathon 2026 Preliminary Round Automated Evaluation Engine.
Evaluates mission reports against the official 100-point rubric from the competition PDF.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from skytrack_mcp.report.parser import is_synthetic_report


FLIGHT_AREA_POLYGON: List[Tuple[float, float]] = [
    (-112.55, 71.20),
    (237.81, 43.63),
    (267.37, -185.41),
    (205.38, -229.27),
    (-96.18, -232.80),
]

FIRE_POINT_WORLD = (-83.74, -28.18)
SPAWN_POINT_WORLD = (203.684, -153.697, 0.452)
FIRE_POINT_LOCAL = (
    FIRE_POINT_WORLD[0] - SPAWN_POINT_WORLD[0],  # -287.424
    FIRE_POINT_WORLD[1] - SPAWN_POINT_WORLD[1],  # +125.517
)


def point_in_polygon(point: Tuple[float, float], polygon: Sequence[Tuple[float, float]]) -> bool:
    """Ray casting algorithm to determine if point (x, y) is inside polygon."""
    x, y = point
    inside = False
    n = len(polygon)
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _safe_float(val: Any) -> Optional[float]:
    """Safely parse a value as float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _verify_video_wraps_ball_drop(
    events: Sequence[Dict[str, Any]],
) -> Tuple[bool, str]:
    """Verify that video recording starts strictly before ball drop and stops strictly after ball drop without interruption."""
    start_indices: List[int] = []
    drop_indices: List[int] = []
    stop_indices: List[int] = []

    for idx, ev in enumerate(events):
        ev_type = str(ev.get("event", ""))
        ev_data = ev.get("data", {}) or {}
        status_str = str(ev_data.get("status", "")).lower()
        op_str = str(ev_data.get("operation", "")).lower()

        if (
            ev_type == "RECORDING_STARTED"
            or "recording started" in status_str
            or (ev_type == "CAMERA_TRIGGER" and op_str in ("recording_on", "start-recording-video"))
        ):
            start_indices.append(idx)

        if ev_type in ("BALL_DROP", "PAYLOAD_TRIGGER"):
            if ev_type == "BALL_DROP" or op_str in ("drop-ball", "drop_payload", ""):
                drop_indices.append(idx)

        if (
            ev_type == "RECORDING_STOPPED"
            or "recording stopped" in status_str
            or (ev_type == "CAMERA_TRIGGER" and op_str in ("recording_off", "stop-recording-video"))
        ):
            stop_indices.append(idx)

    if not drop_indices:
        return False, "Missing BALL_DROP event in execution_events"
    if not start_indices:
        return False, "Missing recording start event in execution_events"
    if not stop_indices:
        return False, "Missing recording stop event in execution_events"

    # For each drop event, verify it is wrapped by an active uninterrupted recording session
    for drop_idx in drop_indices:
        starts_before = [s for s in start_indices if s < drop_idx]
        if not starts_before:
            continue
        active_start = max(starts_before)
        # Check if any stop occurred between active_start and drop_idx
        if any(active_start < st < drop_idx for st in stop_indices):
            continue

        stops_after = [st for st in stop_indices if st > drop_idx]
        if not stops_after:
            continue
        active_stop = min(stops_after)
        # Check if any start occurred between drop_idx and active_stop
        if any(drop_idx < s < active_stop for s in start_indices):
            continue

        return (
            True,
            f"Verified continuous recording wrap: start_event=#{active_start} < drop_event=#{drop_idx} < stop_event=#{active_stop}",
        )

    return (
        False,
        f"Video recording did not continuously wrap ball drop: starts={start_indices}, drops={drop_indices}, stops={stop_indices}",
    )


def _match_waypoints_sequence_in_order(
    defined_wps: Sequence[Dict[str, Any]],
    reached_events: Sequence[Dict[str, Any]],
    horizontal_tol_m: float = 1.0,
    vertical_tol_m: float = 1.0,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Verify that each defined waypoint is reached in chronological sequence order."""
    if not defined_wps:
        return False, []
    matched: List[Dict[str, Any]] = []
    r_idx = 0
    for wd in defined_wps:
        wx = float(wd.get("x", 0.0))
        wy = float(wd.get("y", 0.0))
        wz = float(wd.get("z", 0.0))
        found = False
        while r_idx < len(reached_events):
            re = reached_events[r_idx]
            r_idx += 1
            rx = float(re.get("x", 0.0))
            ry = float(re.get("y", 0.0))
            rz = float(re.get("z", 0.0))
            h_err = math.sqrt((rx - wx) ** 2 + (ry - wy) ** 2)
            v_err = abs(rz - wz)
            if h_err <= horizontal_tol_m and v_err <= vertical_tol_m:
                matched.append(re)
                found = True
                break
        if not found:
            return False, matched
    return len(matched) == len(defined_wps), matched


def score_hackathon_mission_report(
    report_json_path: Path,
    plan_json_path: Optional[Path] = None,
    allow_synthetic: bool = False,
    expected_mission_id: Optional[str] = None,
    expected_execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Score a mission report JSON against the Hackathon 2026 rubric.

    Strict fail-closed evaluation:
    - Enforces world == 'urban'.
    - Enforces >= 5 defined and >= 5 reached waypoints inside polygon and alt >= 35.0m.
    - Patrol length (>=400m) and span (>=120m) computed from reached waypoints sequence.
    - Video recording must wrap ball drop strictly in execution_events.
    - Ball drop must exist in execution_events with error <= 3.0m.
    - RTL must exist in execution_events with phase 'completed' or 'reached_home'.
    - Rejects synthetic reports when allow_synthetic is False.
    - Enforces expected_mission_id and expected_execution_id when provided.
    """
    report_path = Path(report_json_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    meta = data.get("execution_metadata", {})

    scores: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    empty_scores = {
        "mission_success": 0.0,
        "valid_route": 0.0,
        "true_patrol_metrics": 0.0,
        "video_recording_wrapped": 0.0,
        "ball_drop_accuracy": 0.0,
        "rtl_completion": 0.0,
    }

    # Mission ID Gate
    if expected_mission_id is not None:
        clean_expected_mis = str(expected_mission_id).strip().removeprefix("mis-")
        actual_mis = str(meta.get("mission_id", "")).strip().removeprefix("mis-")
        if not clean_expected_mis or actual_mis != clean_expected_mis:
            return {
                "total_score": 0.0,
                "max_score": 100.0,
                "passed_threshold": False,
                "rubric_scores": dict(empty_scores),
                "details": {
                    "error": f"Mission ID mismatch: expected '{clean_expected_mis}', got '{actual_mis}'",
                    "expected_mission_id": clean_expected_mis,
                    "actual_mission_id": actual_mis,
                },
            }

    # Resolve execution_report entry: match expected_execution_id if provided, else default to latest entry
    report_entries = data.get("execution_report") or []
    if not isinstance(report_entries, list) or not report_entries:
        report_entries = [{}]

    if expected_execution_id is not None:
        clean_expected_exec = str(expected_execution_id).strip()
        matching = [
            e for e in report_entries
            if isinstance(e, dict) and str(e.get("execution_id", "")).strip() == clean_expected_exec
        ]
        if not clean_expected_exec or not matching:
            return {
                "total_score": 0.0,
                "max_score": 100.0,
                "passed_threshold": False,
                "rubric_scores": dict(empty_scores),
                "details": {
                    "error": f"Execution ID mismatch or empty: expected '{clean_expected_exec}' not found in execution_report entries",
                    "expected_execution_id": clean_expected_exec,
                    "available_execution_ids": [str(e.get("execution_id", "")).strip() for e in report_entries if isinstance(e, dict)],
                },
            }
        report = matching[-1]
    else:
        report = report_entries[-1]

    summary = report.get("status_summary", {}) if isinstance(report, dict) else {}
    events = report.get("execution_events", []) if isinstance(report, dict) else []

    # Synthetic Provenance Gate
    is_synth = is_synthetic_report(data, report_path)
    if is_synth and not allow_synthetic:
        return {
            "total_score": 0.0,
            "max_score": 100.0,
            "passed_threshold": False,
            "rubric_scores": dict(empty_scores),
            "details": {
                "error": "Synthetic report rejected: allow_synthetic is False",
                "provenance": "synthetic",
            },
        }

    world = str(meta.get("world") or summary.get("world") or "").lower()
    world_valid = (world == "urban")

    # Global World Gate: only urban missions are eligible for Hackathon scoring
    if not world_valid:
        empty_scores = {
            "mission_success": 0.0,
            "valid_route": 0.0,
            "true_patrol_metrics": 0.0,
            "video_recording_wrapped": 0.0,
            "ball_drop_accuracy": 0.0,
            "rtl_completion": 0.0,
        }
        return {
            "total_score": 0.0,
            "max_score": 100.0,
            "passed_threshold": False,
            "rubric_scores": empty_scores,
            "details": {
                "error": f"Invalid world '{world}': only 'urban' missions are eligible for Hackathon scoring",
                "world": world,
                "world_valid": False,
            },
        }

    # Criterion 1: Mission executes successfully to completion (22 pts)
    final_status = summary.get("final_status") or meta.get("status", "UNKNOWN")
    status_ok = str(final_status).lower() in ("succeeded", "completed")
    failure_ok = (summary.get("failure_reason") is None) and (summary.get("failure_category_id") is None)
    terminal_event = any(
        e.get("event") == "MISSION_END"
        or (e.get("event") == "RTL" and str((e.get("data") or {}).get("phase", "")).lower() == "completed")
        for e in events
    )
    c1_pass = world_valid and status_ok and failure_ok and terminal_event
    scores["mission_success"] = 22.0 if c1_pass else 0.0
    details["final_status"] = final_status
    details["mission_success_checks"] = {
        "world": world,
        "world_valid": world_valid,
        "status_ok": status_ok,
        "failure_ok": failure_ok,
        "terminal_event": terminal_event,
    }

    # Criterion 2: Valid route (>=5 waypoints, inside flight area, Z >= 35m, all visited in order) (15 pts)
    ALTITUDE_MIN_M = 35.0 - 1e-6  # 35.0m threshold allowing IEEE-754 precision (~3e-14) while strictly rejecting deviations >= 1mm (such as 34.999 or 34.9)
    waypoints_def = summary.get("waypoints_defined", [])
    reached_wps = [e.get("data", {}) for e in events if e.get("event") == "WAYPOINT_REACHED"]

    count_def_valid = len(waypoints_def) >= 5
    count_reached_valid = len(reached_wps) >= 5 and (len(reached_wps) >= len(waypoints_def))
    sequence_matched, matched_reached = _match_waypoints_sequence_in_order(waypoints_def, reached_wps)

    inside_poly_def = bool(waypoints_def) and all(point_in_polygon((w["x"], w["y"]), FLIGHT_AREA_POLYGON) for w in waypoints_def)
    inside_poly_reached = bool(reached_wps) and all(point_in_polygon((w["x"], w["y"]), FLIGHT_AREA_POLYGON) for w in reached_wps)
    alt_def_valid = bool(waypoints_def) and all(float(w.get("z", 0.0)) >= ALTITUDE_MIN_M for w in waypoints_def)
    alt_reached_valid = bool(reached_wps) and all(float(w.get("z", 0.0)) >= ALTITUDE_MIN_M for w in reached_wps)

    c2_pass = (
        world_valid
        and count_def_valid
        and count_reached_valid
        and sequence_matched
        and inside_poly_def
        and inside_poly_reached
        and alt_def_valid
        and alt_reached_valid
    )
    scores["valid_route"] = 15.0 if c2_pass else 0.0
    details["route_checks"] = {
        "world_valid": world_valid,
        "waypoint_count": len(waypoints_def),
        "waypoint_count_defined": len(waypoints_def),
        "waypoint_count_reached": len(reached_wps),
        "count_def_valid": count_def_valid,
        "count_reached_valid": count_reached_valid,
        "sequence_matched": sequence_matched,
        "all_def_inside_polygon": inside_poly_def,
        "all_reached_inside_polygon": inside_poly_reached,
        "all_def_alt_ge_35m": alt_def_valid,
        "all_reached_alt_ge_35m": alt_reached_valid,
    }

    # Criterion 3: True patrol (route length >= 400m, span >= 120m in both X and Y) (15 pts)
    pts_for_patrol = reached_wps if (world_valid and len(reached_wps) >= 5) else []
    distinct_pts = len(set((round(float(w.get("x", 0.0)), 1), round(float(w.get("y", 0.0)), 1)) for w in pts_for_patrol))
    total_len = 0.0
    for i in range(len(pts_for_patrol) - 1):
        p0 = pts_for_patrol[i]
        p1 = pts_for_patrol[i + 1]
        total_len += math.sqrt((p1["x"] - p0["x"]) ** 2 + (p1["y"] - p0["y"]) ** 2)

    xs = [w["x"] for w in pts_for_patrol]
    ys = [w["y"] for w in pts_for_patrol]
    span_x = max(xs) - min(xs) if xs else 0.0
    span_y = max(ys) - min(ys) if ys else 0.0

    length_valid = total_len >= 400.0
    span_valid = (span_x >= 120.0) and (span_y >= 120.0)
    distinct_valid = distinct_pts >= 5
    c3_pass = world_valid and (len(pts_for_patrol) >= 5) and distinct_valid and length_valid and span_valid
    scores["true_patrol_metrics"] = 15.0 if c3_pass else 0.0
    details["patrol_metrics"] = {
        "reached_waypoints_evaluated": len(pts_for_patrol),
        "distinct_locations_visited": distinct_pts,
        "total_2d_length_m": round(total_len, 2),
        "span_x_m": round(span_x, 2),
        "span_y_m": round(span_y, 2),
        "length_valid": length_valid,
        "span_valid": span_valid,
        "distinct_valid": distinct_valid,
    }

    # Criterion 4: Video recording wraps the drop (start < drop < stop) (18 pts)
    c4_pass, c4_reason = _verify_video_wraps_ball_drop(events=events)
    scores["video_recording_wrapped"] = 18.0 if c4_pass else 0.0
    details["video_recording"] = {
        "passed": c4_pass,
        "evidence": c4_reason,
    }

    # Criterion 5: Drop firefighting ball on fire point (<= 3 m horizontal) (18 pts)
    ball_drops = [e for e in events if e.get("event") == "BALL_DROP"]
    drop_accuracy_pass = False
    min_dist_m = 999.0

    if ball_drops:
        drop = ball_drops[0].get("data", {})
        dx_local = float(drop.get("x", 0.0))
        dy_local = float(drop.get("y", 0.0))
        # Strictly evaluate in local ENU frame relative to spawn as defined by SkyTrack telemetry schema
        dist_from_target = math.sqrt(
            (dx_local - FIRE_POINT_LOCAL[0]) ** 2 + (dy_local - FIRE_POINT_LOCAL[1]) ** 2
        )
        min_dist_m = dist_from_target
        if dist_from_target <= 3.0:
            drop_accuracy_pass = True

    scores["ball_drop_accuracy"] = 18.0 if drop_accuracy_pass else 0.0
    details["ball_drop"] = {
        "drop_events_count": len(ball_drops),
        "horizontal_error_m": round(min_dist_m, 3),
        "drop_accuracy_pass": drop_accuracy_pass,
    }

    # Criterion 6: Return to launch via RTL (12 pts)
    rtl_events = [e for e in events if e.get("event") == "RTL"]
    rtl_completed = any(
        str((e.get("data") or {}).get("phase", "")).lower() in ("completed", "reached_home")
        for e in rtl_events
    )
    rtl_pass = (len(rtl_events) > 0) and rtl_completed
    scores["rtl_completion"] = 12.0 if rtl_pass else 0.0
    details["rtl"] = {
        "rtl_events_count": len(rtl_events),
        "rtl_completed": rtl_completed,
        "passed": rtl_pass,
    }

    # Dossier requirements (non-scoring checklist from PDF)
    vid_dur = _safe_float(meta.get("submission_video_duration_s"))
    details["submission_dossier"] = {
        "report_url_public": bool(meta["report_url"]) if "report_url" in meta else "UNKNOWN",
        "video_duration_le_90s": (vid_dur <= 90.0) if vid_dur is not None else "UNKNOWN",
        "team_information_included": bool(meta.get("team") or meta.get("team_name")) if ("team" in meta or "team_name" in meta) else "UNKNOWN",
    }

    total_score = sum(scores.values())

    return {
        "total_score": total_score,
        "max_score": 100.0,
        "passed_threshold": total_score >= 85.0,
        "rubric_scores": scores,
        "details": details,
    }
