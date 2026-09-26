# SkyTrack Review Cycle 1 — Independent Evaluation Report

**Review Date:** 2026-09-26  
**Reviewer:** Independent Reviewer / QA / Evaluation Agent  
**Target:** SkyTrack MCP Server & Agent Skillbook  
**Evaluated Build/Commit:** f605869  

---

## 1. Executive Summary

- **Total Scenarios Evaluated:** 5 (EVAL 1 - EVAL 5) + MCP Component Audits
- **Passed:** 0 (True Verification Passed)
- **Failed:** 5 (All 5 evaluations previously claiming PASS were confirmed as False Positives)
- **Blocked:** 1 (Live telemetry stream blocked by PX4 Gazebo sync loop and missing recreation)
- **Flaky:** 0
- **Overall Build Status:** **BLOCKED / NOT VERIFIED (Critical Defects S1 & S2 Active)**

---

## 2. Critical Findings (S0 / S1)

### BUG-0001: False Verification in Evaluation Harness and Requirement Evaluator (S1 - CRITICAL)
- **Details:** `evals/run_all_evals.py` executed in ~5 seconds by issuing an asynchronous `execute_route_mission` POST request without awaiting drone flight execution or touchdown. `verification.py` evaluated `min_waypoints` against planned waypoint count in `plan.json` rather than actual reached waypoints during flight. In EVAL 1, "Safe Takeoff Altitude" was verified by checking if `world == 'default'`. In EVAL 2, "Collision-Free 3D Trajectory" was verified by checking if `planned_waypoints >= 5`.
- **Reference:** `evals/bugs/BUG-0001.md`

### BUG-0002: Mission Report Harvester Ignores Authentic SkyTrack Mission Report JSON (S1 - CRITICAL)
- **Details:** Authentic SkyTrack simulation flights produce rich, authoritative execution report files (`skytrack-mission-report*.json`) in `ClientData/prj-*/mis-*/` containing `execution_metadata`, `status_summary`, and `execution_events` (`WAYPOINT_REACHED`, `NAVIGATION_STATUS`, `PAYLOAD_TRIGGER`). `src/skytrack_mcp/report/parser.py` completely ignores these files, instead fabricating a synthetic dictionary from static plan files and an instantaneous telemetry snapshot.
- **Reference:** `evals/bugs/BUG-0002.md`

---

## 3. High & Medium Defects (S2 / S3)

### BUG-0003: Simulation Stack Container Recreation Failure on World/Vehicle Change & PX4 Gazebo Timeout (S2 - HIGH)
- **Details:** `start_simulation_stack` rewrites `docker-compose.yml` and calls `docker compose up -d` without `--force-recreate`. As a result, Gazebo remains on the old world (e.g. `default.sdf`) while PX4 restarts with the new world (e.g. `warehouse`), causing `px4-rc.gzsim` to loop for 300 seconds waiting for `/world/warehouse/scene/info`.
- **Reference:** `evals/bugs/BUG-0003.md`

---

## 4. Coordinate & Mission Accuracy Audit

- **Coordinate System Identified:** 
  - Local frame is **ENU** (East = +X, North = +Y, Up = +Z).
  - Python Autonomy local planner uses `(north=..., east=..., alt_m=...)`.
  - GCS API `:20002/mission/v2/execute` accepts ENU coordinates `[x, y, z]`.
- **Quantitative Trajectory Verification Status:** Currently blocked from real-time verification because the evaluation harness does not parse `skytrack-mission-report*.json` reached events or wait for live flights.

---

## 5. Recommended Implementation Order for Implementation Agent

1. **Fix BUG-0002 (Report Parser):** Update `src/skytrack_mcp/report/parser.py` to search for and parse `skytrack-mission-report*.json` so that real flight data, visited coordinates, and events are surfaced to the agent.
2. **Fix BUG-0001 (Verification Matrix & Eval Loop):** 
   - Update `src/skytrack_mcp/report/verification.py` to evaluate actual execution events (`WAYPOINT_REACHED`, `landed_safely`, altitude numbers).
   - Update `evals/run_all_evals.py` to use `run_mission_and_wait_completion` or live observation rather than fire-and-forget assertions.
3. **Fix BUG-0003 (Container Recreate):** Pass `--force-recreate` in `start_simulation_stack` and ensure clean Gazebo/PX4 synchronization.

---

## 6. Acceptance Criteria for Next Build (Review Cycle 2)

- [ ] `tool_skytrack_report_read(mission_id="01M39YY8G8NZXCBMJH8RHH1GWP")` successfully parses and returns events from `skytrack-mission-report.json`.
- [ ] `evaluate_mission_requirements` verifies reached waypoints against `WAYPOINT_REACHED` events and verifies numerical altitude.
- [ ] `evals/run_all_evals.py` actually runs closed-loop flights and fails if the drone does not reach waypoints.
- [ ] No false-success assertions remain in `evals/run_all_evals.py`.
