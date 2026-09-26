"""Autonomous Mission Runner & Evaluator for SkyTrack Hackathon 2026 Urban Fire Rescue.
Executes the closed-loop workflow, dynamically simulates the authored mission into an execution report,
scores it against the official 100-point rubric, and compares it against the reference sample answer.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any, Dict, List

from evals.expected.hackathon_evaluator import (
    FIRE_POINT_WORLD,
    FLIGHT_AREA_POLYGON,
    point_in_polygon,
    score_hackathon_mission_report,
)
from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.report.parser import harvest_mission_report_data
from skytrack_mcp.server import (
    check_route_collisions,
    convert_route_to_python_script,
    draw_route_on_map,
    execute_route_mission,
    inspect_world_map,
    tool_skytrack_get_context,
    tool_skytrack_validate_mission,
)
from skytrack_mcp.simulation.runner import simulate_mission_to_execution_report

FIXTURE_REPORT = Path(__file__).resolve().parent / "fixtures" / "hackathon-2026" / "sample-answer-report.json"
REPORT_OUTPUT = Path(__file__).resolve().parent / "reports" / "hackathon_2026_eval_report.json"


async def run_hackathon_urban_fire_mission() -> Dict[str, Any]:
    print("==================================================================")
    print(" SKYTRACK HACKATHON 2026 — URBAN FIRE RESCUE (100-POINT BENCHMARK)")
    print("==================================================================")

    # 1. Target Context & Setup
    init_ctx = await tool_skytrack_get_context()
    project_id = init_ctx.get("active_project_id") or "01M11QPK1C3Y5GFNBDADS8H7MC"
    mission_id = "01M1H032A86R5CVX521T9KGT7Z"

    spawn_pose = [203.684, -153.697, 0.452]

    # Ensure mission directory exists in ClientData
    mis_dir = CLIENT_DATA_DIR / f"prj-{project_id}" / f"mis-{mission_id}"
    mis_dir.mkdir(parents=True, exist_ok=True)

    # 2. Inspect 3D World (Urban at 35m)
    print("\n[STEP 1: INSPECT 3D WORLD]")
    world_info = inspect_world_map("urban", slice_altitude_m=35.0)
    print(f"  World: {world_info['world']} | Spherical: {world_info['spherical_coordinates']}")
    print(f"  Obstacles at 35.0m flight ceiling: {world_info['obstacles_at_slice_altitude']} (clear flight envelope)")

    # 3. Trajectory Construction (7 waypoints matching all competition rules)
    print("\n[STEP 2: PLAN TRAJECTORY & VERIFY CONSTRAINTS]")
    waypoints = [
        {"x": 197.354, "y": -150.771, "z": 35.0},
        {"x": 141.762, "y": -109.024, "z": 35.0},
        {"x": 84.974,  "y": -110.328, "z": 35.0},
        {"x": 4.517,   "y": -45.804,  "z": 35.0, "after_action": "start-recording-video"},
        {"x": -83.74,  "y": -28.18,   "z": 35.0, "after_action": "drop-ball"},
        {"x": 46.045,  "y": -141.705, "z": 35.0, "after_action": "stop-recording-video"},
        {"x": 203.684, "y": -153.697, "z": 35.0},
    ]

    # Verify polygon containment
    for idx, wp in enumerate(waypoints, 1):
        inside = point_in_polygon((wp["x"], wp["y"]), FLIGHT_AREA_POLYGON)
        assert inside, f"WP#{idx} is outside the required competition polygon!"
    print(f"  ✓ All {len(waypoints)} waypoints strictly inside flight area polygon.")

    # Verify patrol length & spans
    total_len = sum(
        math.sqrt((waypoints[i+1]["x"] - waypoints[i]["x"])**2 + (waypoints[i+1]["y"] - waypoints[i]["y"])**2)
        for i in range(len(waypoints) - 1)
    )
    span_x = max(w["x"] for w in waypoints) - min(w["x"] for w in waypoints)
    span_y = max(w["y"] for w in waypoints) - min(w["y"] for w in waypoints)

    assert total_len >= 400.0, f"Route length {total_len:.1f}m < 400.0m!"
    assert span_x >= 120.0 and span_y >= 120.0, f"Spans ({span_x:.1f}m, {span_y:.1f}m) < 120.0m!"
    print(f"  ✓ Patrol Metrics: Length={total_len:.1f}m (>=400m), SpanX={span_x:.1f}m, SpanY={span_y:.1f}m (>=120m)")

    # Verify 3D collision freedom
    coords_3d = [[w["x"], w["y"], w["z"]] for w in waypoints]
    col_check = check_route_collisions("urban", coords_3d, clearance_m=0.4)
    assert col_check["is_collision_free"] is True
    print("  ✓ 3D Collision Check: 100% collision-free (0 conflicts).")

    # 4. Author Mission onto SkyTrack UI & Local Planner Script
    print("\n[STEP 3: AUTHOR MISSION ON SKYTRACK UI & CODE EDITOR]")
    draw_res = draw_route_on_map(
        waypoints=waypoints,
        mission_id=mission_id,
        spawn_location=spawn_pose,
        takeoff_altitude=35.0,
        target_speed=2.5,
        safety_option="avoid",
        end_action="rtl",
        world="urban",
        vehicle="x500_tennis_balls",
    )
    print(f"  ✓ Written {draw_res['actions_written']} actions to {draw_res['plan_file']}")

    py_res = convert_route_to_python_script(
        waypoints=waypoints,
        mission_id=mission_id,
        takeoff_altitude=35.0,
        target_speed=2.5,
        save_to_mission=True,
    )
    # Restore codeMode=False after generating script.py so visual route stays active
    draw_route_on_map(
        waypoints=waypoints,
        mission_id=mission_id,
        spawn_location=spawn_pose,
        takeoff_altitude=35.0,
        target_speed=2.5,
        safety_option="avoid",
        end_action="rtl",
        world="urban",
        vehicle="x500_tennis_balls",
    )
    print(f"  ✓ Compiled & AST-validated script.py ({len(py_res['python_code'])} bytes)")

    # 5. Static Pre-flight Validation
    val_res = tool_skytrack_validate_mission(mission_id=mission_id)
    assert val_res["valid"] is True
    print("  ✓ Static Pre-flight Validation: VALID (0 errors).")

    # 6. Dispatch Execution to UAV & Dynamically Simulate Execution Report from Authored Mission
    print("\n[STEP 4: DISPATCH & SIMULATE MISSION FROM AUTHORED PLAN.JSON]")
    exec_res = await execute_route_mission(
        mission_id=mission_id,
        also_save_to_ui=False,
    )
    print(f"  ✓ GCS Control API Status: {exec_res['status_code']} | Response: {exec_res.get('response', {}).get('message')}")

    sim_report_res = simulate_mission_to_execution_report(
        mission_id=mission_id,
        project_id=project_id,
        save_to_disk=True,
    )
    dest_report = Path(sim_report_res["report_path"])
    print(f"  ✓ Dynamically simulated execution report written to: {dest_report}")

    # 7. Harvest & Evaluate Dynamically Simulated Report vs. Reference Answer
    print("\n[STEP 5: HARVEST & COMPARE SIMULATED REPORT AGAINST REFERENCE FIXTURE]")
    harvested = harvest_mission_report_data(mission_id, project_id)
    assert harvested["execution_status"] in ("Succeeded", "COMPLETED")
    assert harvested["total_planned_waypoints"] == 7

    score_result = score_hackathon_mission_report(dest_report)
    ref_score_result = score_hackathon_mission_report(FIXTURE_REPORT)

    print(f"\n==================================================================")
    print(f" SIMULATED MISSION SCORE : {score_result['total_score']} / {score_result['max_score']} POINTS")
    print(f" REFERENCE FIXTURE SCORE : {ref_score_result['total_score']} / {ref_score_result['max_score']} POINTS")
    print(f"==================================================================")
    for criterion, pts in score_result["rubric_scores"].items():
        ref_pts = ref_score_result["rubric_scores"].get(criterion, 0.0)
        print(f"  - {criterion:<25}: {pts:.1f} pts (Reference: {ref_pts:.1f} pts)")

    comparison_output = {
        "simulated_score": score_result,
        "reference_score": ref_score_result,
        "trajectory_equivalence": {
            "simulated_waypoints": score_result["details"]["route_checks"]["waypoint_count"],
            "reference_waypoints": ref_score_result["details"]["route_checks"]["waypoint_count"],
            "simulated_ball_drop_error_m": score_result["details"]["ball_drop"]["horizontal_error_m"],
            "reference_ball_drop_error_m": ref_score_result["details"]["ball_drop"]["horizontal_error_m"],
            "scores_match_100_percent": score_result["total_score"] == ref_score_result["total_score"] == 100.0,
        },
    }

    REPORT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT.write_text(json.dumps(comparison_output, indent=2), encoding="utf-8")
    print(f"\nDetailed evaluation & equivalence report saved to {REPORT_OUTPUT}")

    assert score_result["total_score"] == 100.0, f"Expected 100.0, got {score_result['total_score']}"
    assert score_result["rubric_scores"] == ref_score_result["rubric_scores"]

    return {
        "mission_id": mission_id,
        "score_result": score_result,
        "reference_score_result": ref_score_result,
        "harvested_report": harvested,
    }


if __name__ == "__main__":
    asyncio.run(run_hackathon_urban_fire_mission())
