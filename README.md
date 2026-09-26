# SkyTrack MCP Integration & Skill System

Model Context Protocol (MCP) server and autonomous agent skillbook for **SkyTrack Mission Studio**.

This package provides a production-grade autonomous agent operating layer that allows an AI model (Claude, Cursor, Gemini) to understand UAV mission assignments, inspect 3D Gazebo environments, author collision-free visual routes or Python autonomy scripts, manage the simulation runtime, monitor telemetry in real-time, and verify mission outcomes against empirical evidence.

---

## 1. Quickstart

### Installation
```bash
git clone https://github.com/phucdang/skytrack-mcp.git
cd skytrack-mcp
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Running Tests & Evaluation Suite
```bash
# Run Unit & MCP Wire Protocol Tests
pytest -v

# Run the 5 Mandatory Autonomous Closed-Loop Evaluations (EVAL 1 - EVAL 5)
PYTHONPATH=. python evals/run_all_evals.py
```

### Adding to Claude Code
```bash
claude mcp add skytrack -- /Users/phucdang/Documents/skytrack-mcp/.venv/bin/skytrack-mcp
```

### Adding to Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "skytrack": {
      "command": "/Users/phucdang/Documents/skytrack-mcp/.venv/bin/skytrack-mcp",
      "args": []
    }
  }
}
```

---

## 2. Real End-to-End Walkthrough

Here is how an AI agent autonomously executes a natural-language mission assignment using this MCP:

### User Request
> *"In the warehouse world, take off to 3.5m, inspect storage racks 5, 4, and 3, drop one firefighting ball on each rack, return home, land safely, and verify the mission."*

### Agent Autonomous Execution Steps:

```
[STEP 1: UNDERSTAND TASK]
  → skytrack-task-understanding decomposes request:
    - World: 'warehouse' | Vehicle: 'x500_tennis_balls_no_cam' (5-ball capacity)
    - Altitude: 3.5m | Speed: 2.0 m/s
    - Mandatory actions: drop-ball at Rack 5, 4, 3 | End: RTL/Land

[STEP 2: OBSERVE CONTEXT]
  → Calls `tool_skytrack_get_context()`:
    - Active Project: 01M11QPK1C3Y5GFNBDADS8H7MC ("UAV")
    - Active Mission: 01M39QD97035MQVDQ52129D4WJ
    - Simulator: Healthy (7 containers active)

[STEP 3: WORLD INSPECTION & COLLISION AVOIDANCE]
  → Calls `tool_skytrack_inspect_world("warehouse", slice_altitude_m=3.5)`:
    - Identifies storage racks at height 2.83m.
    - Identifies vertical structural pillar `pole2` at [0.43, -2.34], height 6.04m.
  → Plans corridor waypoint [2.63, -1.0, 3.5] to safely bypass pole2.
  → Calls `check_route_collisions("warehouse", waypoints, clearance_m=0.4)`:
    - Result: `is_collision_free: true`, 0 conflicts.

[STEP 4: MISSION AUTHORING & VALIDATION]
  → Calls `draw_route_on_map(waypoints, mission_id="01M39QD97035MQVDQ52129D4WJ")`:
    - Writes 12 actions into `plan.json` (displays immediately on SkyTrack Map UI).
  → Calls `convert_route_to_python_script(...)`:
    - Compiles and AST-validates `script.py` using `local_planner` SDK.
  → Calls `tool_skytrack_validate_mission()`:
    - Pre-flight check: Valid (0 errors, 3 ball drops within 5-ball capacity).

[STEP 5: SIMULATION & REAL-TIME OBSERVATION]
  → Calls `execute_route_mission(mission_id=...)`:
    - GCS Backend (:20002) executes mission on drone.
  → Calls `tool_skytrack_simulation_observe(max_duration_s=120)`:
    - Telemetry poller tracks: ON_GROUND -> TAKEOFF -> IN_AIR -> LANDING -> ON_GROUND.
    - Confirms safe touchdown with 100% battery margin.

[STEP 6: REPORT HARVESTING & EVIDENCE VERIFICATION]
  → Calls `tool_skytrack_report_read()`:
    - Compiles `flight_report.json` and `flight_report.md`.
  → Calls `tool_skytrack_verify_mission_requirements()`:
    - Matrix:
      | Requirement | Expected | Observed | Status |
      | Planned Waypoints | 5 waypoints | 6 waypoints | PASS |
      | Environment Active | warehouse | warehouse | PASS |
      | Safe Landing | ON_GROUND | ON_GROUND | PASS |
    - Final Verdict: **PASS (100% Verified against Evidence)**.
```

---

## 3. Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   Autonomous AI Agent                  │
└───────────────────────────┬────────────────────────────┘
                            │ MCP Protocol (stdio)
                            ▼
┌────────────────────────────────────────────────────────┐
│               SkyTrack MCP Server Layer                │
│   • 45+ Standard Tools across 9 capability groups      │
│   • 8 Managed Resources (`skytrack://...`)             │
│   • 5 Guided Workflow Prompts                          │
└──────────┬─────────────┬─────────────┬───────────┬─────┘
           │             │             │           │
           ▼             ▼             ▼           ▼
   ┌──────────────┐┌───────────┐┌───────────┐┌───────────┐
   │ Adapters     ││ Mission   ││ World/    ││Simulation │
   │ • Cloud API  ││ • Domain  ││ Route     ││ • Docker  │
   │ • Local Sync ││ • Validator│ • SDF 3D  ││ • GCS API │
   │ • MAVLink WS ││ • Patcher ││ • 2D Grid ││ • Telemetry│
   └──────────────┘└───────────┘└───────────┘└───────────┘
```

---

## 4. Documentation Index

- [Architecture Reference](docs/architecture.md)
- [Research & Discovery Findings](docs/research.md)
- [Integration Decision Matrix](docs/integration-decision.md)
- [SkyTrack Capabilities & Vehicles](docs/skytrack-capabilities.md)
- [Canonical Mission Model](docs/mission-model.md)
- [Complete MCP Tools Reference](docs/mcp-tools.md)
- [Computer Use & UI Automation](docs/computer-use.md)
- [3D World Inspection & Geometry](docs/world-inspection.md)
- [Route Planning & Coverage Sweeps](docs/route-planning.md)
- [Simulation Lifecycle & Execution](docs/simulation.md)
- [Report Harvesting & Verification](docs/report-verification.md)
- [Troubleshooting & Self-Healing](docs/troubleshooting.md)
- [Evaluation Results (EVAL 1 - EVAL 5)](docs/eval-results.md)
- [Operational Skillbook](skills/skytrack-operator/SKILL.md)

---

## 5. License
MIT License. Developed for SkyTrack Mission Studio by Uney.
