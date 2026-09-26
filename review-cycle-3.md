# SkyTrack Review Cycle 3 — Adversarial Audit of Hackathon 2026 Implementation

**Review Date:** 2026-09-26  
**Reviewer:** Independent Reviewer / QA / Evaluation Agent  
**Target:** Hackathon 2026 Urban Fire Rescue (`evals/run_hackathon_mission.py`, `evals/expected/hackathon_evaluator.py`, `src/skytrack_mcp/simulation/runner.py`)  
**Evaluated Build/Commit:** f0a1850  

---

## 1. Executive Summary

- **Overall Status:** **REJECTED / REOPENED (2 Critical False-Success / Fixture-Copy Defects Found)**
- While `evals/run_hackathon_mission.py` correctly inspects the `urban` world, plans a valid 7-waypoint route inside the competition polygon at Z=35m, validates 3D obstacle clearance, writes `plan.json` and `script.py`, and dispatches to the GCS API, **Step 5 (lines 140-142) overwrites the mission report by copying the ground-truth `sample-answer-report.json` fixture (`FIXTURE_REPORT`) to `dest_report`**, and **Criterion 4 in `hackathon_evaluator.py` (line 95) hardcodes `video_recording_wrapped = 18.0`**.

---

## 2. Critical Defects Found (S1)

### BUG-0004 (S1 - CRITICAL): `run_hackathon_mission.py` Copies `FIXTURE_REPORT` Instead of Dynamically Re-Simulating Authored Mission
- **Location:** `evals/run_hackathon_mission.py:140-142`
- **Evidence:**
  ```python
  dest_report = mis_dir / "skytrack-mission-report.json"
  if FIXTURE_REPORT.exists():
      dest_report.write_text(FIXTURE_REPORT.read_text(encoding="utf-8"), encoding="utf-8")
  ```
- **Why This Fails Review:** Per `review.md` Section 32 ("False Success is a Critical Failure") and the user's explicit requirement ("see if the agent re-simulates the same answer based on the PDF problem"), the mission report must be generated from the agent's authored mission (`plan.json` and `mission.json`), NOT copied from the answer fixture.
- **Required Fix:**
  1. Implement `simulate_mission_to_execution_report(mission_id: str, project_id: str)` in `src/skytrack_mcp/simulation/runner.py` that reads `mission.json` and `plan.json` from disk and dynamically simulates the flight trajectory and events (`TAKEOFF`, `FLIGHT_MODE_CHANGE`, `NAVIGATION_STATUS`, `WAYPOINT_REACHED`, `RECORDING_STARTED`, `BALL_DROP` at spawn-relative ENU `[wp.x - spawn.x, wp.y - spawn.y, wp.z]`, `RECORDING_STOPPED`, `RTL`, `MISSION_END`).
  2. Remove `FIXTURE_REPORT` copying from `evals/run_hackathon_mission.py` and call `simulate_mission_to_execution_report(mission_id, project_id)` to generate `dest_report` dynamically from the authored mission.
  3. Compare the dynamically generated report against `sample-answer-report.json` to verify trajectory equivalence and 100/100 rubric score.

### BUG-0005 (S1 - CRITICAL): `hackathon_evaluator.py` Hardcodes `video_recording_wrapped = 18.0` Without Verifying Action Ordering
- **Location:** `evals/expected/hackathon_evaluator.py:93-97`
- **Evidence:**
  ```python
  scores["video_recording_wrapped"] = 18.0
  ```
- **Required Fix:**
  1. Update `score_hackathon_mission_report` in `evals/expected/hackathon_evaluator.py` to verify Criterion 4 from actual `RECORDING_STARTED` / `BALL_DROP` / `RECORDING_STOPPED` event order (or `plan.json` `start-recording-video` < `drop-ball` < `stop-recording-video` action indices when scoring a raw report alongside `plan.json`).
  2. Add `test_rubric_penalizes_missing_video_recording` in `tests/test_hackathon_benchmark.py` proving that omitting or misordering video recording drops the score from 100.0 to 82.0.
