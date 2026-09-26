---
name: skytrack-report-analysis
description: Harvests, normalizes, and extracts structured data from flight logs, telemetry traces, and sensor captures into official reports.
---

# SkyTrack Report Analysis Skill

## Purpose
Collects and structures post-flight data from across multiple distributed runtime sources: container logs (`skytrack-autonomy`), PX4 flight logs (`*.ulg`), captured images (`captures/`), video recordings (`recordings/`), and MAVLink telemetry history into a normalized `flight_report.json` and human-readable Markdown report.

## Trigger Conditions
- Triggered immediately after the drone confirms touchdown (`ON_GROUND`) at the end of a simulation run.
- Triggered when reviewing historical mission outcomes.

## Relevant MCP Tools
- `tool_skytrack_report_read(mission_id)`
- `tool_skytrack_report_export(mission_id, output_dir)`
- `tool_skytrack_logs(tail_lines=150)`
- `harvest_flight_report(mission_id)`

## Report Analysis Procedure
1. **Harvest Runtime Data:** Call `harvest_flight_report(mission_id)` to collect latest execution logs, final coordinates, battery remaining, and capture lists.
2. **Normalize Metrics:**
   - Planned vs. Executed waypoints.
   - Cruise speed and altitude envelope.
   - Total flight duration in seconds.
   - Final landed state and terminal coordinates.
3. **Verify Output Artifacts:**
   - Confirm captured images exist in `ClientData/prj-.../mis-.../media/captures/`.
   - Confirm video recordings exist in `ClientData/prj-.../mis-.../media/recordings/`.
4. **Export Report Files:** Ensure `flight_report.json` and `flight_report.md` are persisted in the mission directory.
