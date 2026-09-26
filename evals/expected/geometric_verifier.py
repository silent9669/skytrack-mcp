"""Independent Reviewer Geometric Verification Library.
Implements pure deterministic spatial math strictly independent of production code.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple


def distance_3d(p1: Sequence[float], p2: Sequence[float]) -> float:
    """Calculate 3D Euclidean distance between two points [x, y, z]."""
    return math.sqrt(
        (p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2
    )


def horizontal_distance(p1: Sequence[float], p2: Sequence[float]) -> float:
    """Calculate 2D horizontal distance (XY plane) between two points."""
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)


def altitude_error(actual_z: float, expected_z: float) -> float:
    """Calculate absolute vertical altitude error."""
    return abs(actual_z - expected_z)


def compute_route_length(points: Sequence[Sequence[float]]) -> float:
    """Calculate cumulative route path length across an ordered sequence of 3D points."""
    if len(points) < 2:
        return 0.0
    total = 0.0
    for idx in range(len(points) - 1):
        total += distance_3d(points[idx], points[idx + 1])
    return total


def verify_waypoint_reached(
    actual_pos: Sequence[float],
    expected_pos: Sequence[float],
    horizontal_tolerance_m: float = 0.5,
    vertical_tolerance_m: float = 0.35,
) -> Dict[str, Any]:
    """Verify whether a single visited position satisfies 3D waypoint tolerances."""
    h_err = horizontal_distance(actual_pos, expected_pos)
    v_err = altitude_error(actual_pos[2], expected_pos[2])
    total_err = distance_3d(actual_pos, expected_pos)

    passed = (h_err <= horizontal_tolerance_m) and (v_err <= vertical_tolerance_m)
    return {
        "passed": passed,
        "horizontal_error_m": round(h_err, 3),
        "vertical_error_m": round(v_err, 3),
        "total_3d_error_m": round(total_err, 3),
        "horizontal_tolerance_m": horizontal_tolerance_m,
        "vertical_tolerance_m": vertical_tolerance_m,
    }


def verify_waypoint_sequence(
    actual_events: List[Dict[str, Any]],
    expected_waypoints: List[Dict[str, float]],
    horizontal_tolerance_m: float = 0.75,
) -> Dict[str, Any]:
    """Verify that waypoints were reached in the exact requested sequence.
    Extracts WAYPOINT_REACHED events from authentic flight reports.
    """
    reached_events = [e for e in actual_events if e.get("event") == "WAYPOINT_REACHED"]

    match_results = []
    all_matched = True

    if len(reached_events) < len(expected_waypoints):
        all_matched = False

    for idx, exp in enumerate(expected_waypoints):
        if idx >= len(reached_events):
            match_results.append({
                "expected_index": idx + 1,
                "status": "NOT_REACHED",
                "expected_coords": [exp["x"], exp["y"], exp.get("z", 2.5)],
            })
            all_matched = False
            continue

        act_data = reached_events[idx].get("data", {})
        act_coords = [float(act_data.get("x", 0.0)), float(act_data.get("y", 0.0)), float(act_data.get("z", 0.0))]
        exp_coords = [exp["x"], exp["y"], exp.get("z", act_coords[2])]

        check = verify_waypoint_reached(act_coords, exp_coords, horizontal_tolerance_m=horizontal_tolerance_m)
        if not check["passed"]:
            all_matched = False

        match_results.append({
            "expected_index": idx + 1,
            "actual_event_index": act_data.get("wp_index", idx + 1),
            "expected_coords": exp_coords,
            "actual_coords": act_coords,
            "check": check,
            "status": "PASS" if check["passed"] else "FAIL",
        })

    return {
        "sequence_verified": all_matched,
        "expected_count": len(expected_waypoints),
        "reached_count": len(reached_events),
        "items": match_results,
    }
