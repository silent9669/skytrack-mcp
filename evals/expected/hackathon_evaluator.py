"""Hackathon 2026 Preliminary Round Automated Evaluation Engine.
Evaluates mission reports against the official 100-point rubric from the competition PDF.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


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


def _verify_video_wraps_ball_drop(
    events: Sequence[Dict[str, Any]],
    actions_defined: Optional[Sequence[Dict[str, Any]]] = None,
    plan_json_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Verify that video recording starts strictly before ball drop and stops strictly after ball drop."""
    # 1. Check explicit plan.json if provided or if actions_defined is embedded
    actions_list: List[Dict[str, Any]] = []
    if plan_json_path and Path(plan_json_path).exists():
        try:
            plan_data = json.loads(Path(plan_json_path).read_text(encoding="utf-8"))
            for seq in plan_data.get("sequences", []):
                actions_list.extend(seq.get("actions", []))
        except Exception:
            pass
    elif actions_defined:
        actions_list = list(actions_defined)

    # 2. Check execution_events timeline first
    start_ev_idx: Optional[int] = None
    drop_ev_idx: Optional[int] = None
    stop_ev_idx: Optional[int] = None

    for idx, ev in enumerate(events):
        ev_type = str(ev.get("event", ""))
        ev_data = ev.get("data", {}) or {}
        status_str = str(ev_data.get("status", "")).lower()
        op_str = str(ev_data.get("operation", "")).lower()

        if start_ev_idx is None and (
            ev_type == "RECORDING_STARTED"
            or "recording started" in status_str
            or (ev_type == "CAMERA_TRIGGER" and op_str in ("recording_on", "start-recording-video"))
        ):
            start_ev_idx = idx

        if drop_ev_idx is None and ev_type in ("BALL_DROP", "PAYLOAD_TRIGGER"):
            if ev_type == "BALL_DROP" or op_str in ("drop-ball", "drop_payload", ""):
                drop_ev_idx = idx

        if (
            ev_type == "RECORDING_STOPPED"
            or "recording stopped" in status_str
            or (ev_type == "CAMERA_TRIGGER" and op_str in ("recording_off", "stop-recording-video"))
        ):
            stop_ev_idx = idx

    if start_ev_idx is not None or stop_ev_idx is not None:
        if (
            start_ev_idx is not None
            and drop_ev_idx is not None
            and stop_ev_idx is not None
            and start_ev_idx < drop_ev_idx < stop_ev_idx
        ):
            return (
                True,
                f"Verified in execution_events: start_event=#{start_ev_idx} < drop_event=#{drop_ev_idx} < stop_event=#{stop_ev_idx}",
            )
        return (
            False,
            f"Invalid or incomplete recording event order: start={start_ev_idx}, drop={drop_ev_idx}, stop={stop_ev_idx}",
        )

    # 3. Fallback to checking plan.json / actions_defined action ordering if events had no camera markers
    if actions_list:
        act_start_idx: Optional[int] = None
        act_drop_idx: Optional[int] = None
        act_stop_idx: Optional[int] = None

        for idx, act in enumerate(actions_list):
            t = str(act.get("type", "")).lower()
            after = str(act.get("after_action", "")).lower()
            if act_start_idx is None and (
                t in ("start-recording-video", "recording_on")
                or after in ("start-recording-video", "recording_on")
            ):
                act_start_idx = idx
            if act_drop_idx is None and (
                t in ("drop-ball", "drop_payload") or after in ("drop-ball", "drop_payload")
            ):
                act_drop_idx = idx
            if t in ("stop-recording-video", "recording_off") or after in (
                "stop-recording-video",
                "recording_off",
            ):
                act_stop_idx = idx

        if (
            act_start_idx is not None
            and act_drop_idx is not None
            and act_stop_idx is not None
            and act_start_idx < act_drop_idx < act_stop_idx
        ):
            return (
                True,
                f"Verified in plan actions: start_action=#{act_start_idx} < drop_action=#{act_drop_idx} < stop_action=#{act_stop_idx}",
            )
        return (
            False,
            f"Invalid or missing recording action order in plan: start={act_start_idx}, drop={act_drop_idx}, stop={act_stop_idx}",
        )

    return False, "Missing video recording start/stop wrapping the ball drop"


def score_hackathon_mission_report(
    report_json_path: Path,
    plan_json_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Score a mission report JSON against the Hackathon 2026 rubric."""
    report_path = Path(report_json_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    meta = data.get("execution_metadata", {})
    report = data.get("execution_report", [{}])[0]
    summary = report.get("status_summary", {})
    events = report.get("execution_events", [])

    if plan_json_path is None:
        sibling_plan = report_path.parent / "plan.json"
        if sibling_plan.exists():
            plan_json_path = sibling_plan

    scores: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    # Criterion 1: Mission executes successfully to completion (22 pts)
    final_status = summary.get("final_status") or meta.get("status", "UNKNOWN")
    c1_pass = final_status.lower() in ("succeeded", "completed")
    scores["mission_success"] = 22.0 if c1_pass else 0.0
    details["final_status"] = final_status

    # Criterion 2: Valid route (>=5 waypoints, inside flight area, Z >= 35m, all visited) (15 pts)
    waypoints = summary.get("waypoints_defined", [])
    count_valid = len(waypoints) >= 5
    inside_poly = all(point_in_polygon((w["x"], w["y"]), FLIGHT_AREA_POLYGON) for w in waypoints)
    alt_valid = all(float(w.get("z", 0.0)) >= 34.9 for w in waypoints)
    c2_pass = count_valid and inside_poly and alt_valid
    scores["valid_route"] = 15.0 if c2_pass else 0.0
    details["route_checks"] = {
        "waypoint_count": len(waypoints),
        "count_valid": count_valid,
        "all_inside_polygon": inside_poly,
        "all_alt_ge_35m": alt_valid,
    }

    # Criterion 3: True patrol (route length >= 400m, span >= 120m in both X and Y) (15 pts)
    total_len = 0.0
    for i in range(len(waypoints) - 1):
        p0 = waypoints[i]
        p1 = waypoints[i + 1]
        total_len += math.sqrt((p1["x"] - p0["x"]) ** 2 + (p1["y"] - p0["y"]) ** 2)

    xs = [w["x"] for w in waypoints]
    ys = [w["y"] for w in waypoints]
    span_x = max(xs) - min(xs) if xs else 0.0
    span_y = max(ys) - min(ys) if ys else 0.0

    length_valid = total_len >= 400.0
    span_valid = (span_x >= 120.0) and (span_y >= 120.0)
    c3_pass = length_valid and span_valid
    scores["true_patrol_metrics"] = 15.0 if c3_pass else 0.0
    details["patrol_metrics"] = {
        "total_2d_length_m": round(total_len, 2),
        "span_x_m": round(span_x, 2),
        "span_y_m": round(span_y, 2),
        "length_valid": length_valid,
        "span_valid": span_valid,
    }

    # Criterion 4: Video recording wraps the drop (start < drop < stop) (18 pts)
    c4_pass, c4_reason = _verify_video_wraps_ball_drop(
        events=events,
        actions_defined=summary.get("actions_defined"),
        plan_json_path=plan_json_path,
    )
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
        dist_from_target = math.sqrt(
            (dx_local - FIRE_POINT_LOCAL[0]) ** 2 + (dy_local - FIRE_POINT_LOCAL[1]) ** 2
        )
        min_dist_m = dist_from_target
        if dist_from_target <= 3.0:
            drop_accuracy_pass = True
    else:
        for w in waypoints:
            dist = math.sqrt((w["x"] - FIRE_POINT_WORLD[0]) ** 2 + (w["y"] - FIRE_POINT_WORLD[1]) ** 2)
            if dist < min_dist_m:
                min_dist_m = dist
        if min_dist_m <= 3.0:
            drop_accuracy_pass = True

    scores["ball_drop_accuracy"] = 18.0 if drop_accuracy_pass else 0.0
    details["ball_drop"] = {
        "drop_events_count": len(ball_drops),
        "horizontal_error_m": round(min_dist_m, 3),
        "drop_accuracy_pass": drop_accuracy_pass,
    }

    # Criterion 6: Return to launch via RTL (12 pts)
    rtl_events = [e for e in events if e.get("event") == "RTL"]
    rtl_pass = len(rtl_events) > 0 or final_status.lower() in ("succeeded", "completed")
    scores["rtl_completion"] = 12.0 if rtl_pass else 0.0
    details["rtl"] = {"rtl_events_count": len(rtl_events), "passed": rtl_pass}

    total_score = sum(scores.values())

    return {
        "total_score": total_score,
        "max_score": 100.0,
        "passed_threshold": total_score >= 85.0,
        "rubric_scores": scores,
        "details": details,
    }
