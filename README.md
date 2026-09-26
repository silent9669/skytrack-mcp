# SkyTrack MCP Server

Model Context Protocol (MCP) server for **SkyTrack Mission Studio**.

Enables AI agents (Claude, Cursor, Gemini) to inspect 3D Gazebo environments, author missions (interactive visual routes & ROS 2 Python autonomy scripts), operate the SkyTrack desktop application and Cloud API, execute simulations, and verify flight outcomes against real physical reports.

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│             AI Agent (Claude / Cursor / Gemini)             │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP Protocol (stdio / JSON-RPC)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  SkyTrack MCP Server Layer                  │
│  • Mission Authoring: visual route (plan.json) & script.py  │
│  • 3D Gazebo World Inspection & AABB Collision Guard        │
│  • Autonomy SDK Levels 1–6 (local_planner / skytrack_autonomy)│
│  • Cloud BFF API & Local ClientData Storage Synchronization │
│  • Docker Simulation Stack Lifecycle & MAVLink Telemetry    │
│  • Authentic Mission Report Harvesting & Rubric Evaluation  │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌──────────────────────────────┐┌──────────────────────────────┐
│   SkyTrack Desktop & Cloud   ││    Docker Simulation Stack   │
│  • Electron UI / ClientData  ││  • Gazebo Harmonic 3D Sim    │
│  • platform.getskytrack.com  ││  • PX4 SITL Flight Controller│
│  • 3D Map / Code Mission View││  • ROS 2 Jazzy Autonomy      │
│  • Real-time Flight Status   ││  • GCS Backend (:20002)      │
└──────────────────────────────┘└──────────────────────────────┘
```

---

## 2. Installation & Setup

### Prerequisites
- macOS / Linux
- Python 3.10+ (Python 3.12 recommended)
- [uv](https://github.com/astral-sh/uv) or `pip`
- Docker Desktop (for SkyTrack simulation stack)

### 1. Clone & Install
```bash
git clone https://github.com/silent9669/skytrack-mcp.git
cd skytrack-mcp

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Verify Installation
```bash
# Run complete test suite (40 unit, live, regression & benchmark tests)
pytest -v

# Run the Hackathon 2026 Urban Fire Rescue Autonomous Mission
python evals/run_hackathon_mission.py
```

### 3. Add to Claude Code CLI
```bash
claude mcp add skytrack -- $(pwd)/.venv/bin/skytrack-mcp
```

### 4. Add to Claude Desktop
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "skytrack": {
      "command": "/absolute/path/to/skytrack-mcp/.venv/bin/skytrack-mcp",
      "args": []
    }
  }
}
```

---

## 3. Supported Autonomy Levels (Levels 1–6)

Aligned 100% with `GetSkyTrack/skytrack-autonomy-example`:

| Level | Capability | Key Motion Steps, Senses & Services |
|---|---|---|
| **Level 1** | **Basics** | `takeoff`, `fly_to(north, east, alt_m)`, `brake`, `land` |
| **Level 2** | **Flight Patterns** | `orbit`, `helix`, `yaw_to`, `mode="coverage"`, `replan_mode="fast"` |
| **Level 3** | **Mission Logic** | Sub-generators (`yield from`), `ctx.senses.battery.percent` (0–100) failsafe |
| **Level 4** | **Camera & Services** | `CameraSense`, `VideoRecorder`, `Snapshot`, `Sprayer`, `Detector` |
| **Level 5** | **Custom Extensions** | Custom `Sense` (`GeofenceSense`), `Skill` (`HoverForSeconds`), `Service` (`TelemetryLogger`), `ControlMode` |
| **Level 6** | **Full-Stack Job** | Integrated site survey: lawnmower sweep + video recording + inspection stills + telemetry CSV + RTL |

To retrieve a verified template for any level:
```python
# MCP Tool: get_autonomy_level_template(level=1..6)
```

---

## 4. Key MCP Tools Summary

- **Environment & UI:** `tool_skytrack_status`, `tool_skytrack_focus`, `tool_ui_snapshot`, `tool_ui_click`
- **World & Collisions:** `inspect_world_map`, `check_route_collisions`, `tool_skytrack_list_worlds`
- **Missions & Cloud:** `tool_skytrack_create_mission`, `draw_route_on_map`, `convert_route_to_python_script`, `sync_mission_to_cloud`
- **Simulation Control:** `manage_simulation_stack`, `execute_route_mission`, `run_mission_and_wait_completion`, `get_uav_telemetry`
- **Verification & Reports:** `harvest_flight_report`, `tool_skytrack_report_read`, `tool_skytrack_verify_mission_requirements`, `validate_uav_python_code`

---

## 5. Repository Structure

```
skytrack-mcp/
├── src/skytrack_mcp/         # MCP server, autonomy SDK, simulation & clients
├── skills/                   # Agent operational skillbook (10 skills)
├── tests/                    # 40 pytest unit, integration, and benchmark tests
├── evals/                    # Test catalog, regressions, and Hackathon runner
│   ├── catalog/              # Formal test specifications (YAML)
│   ├── expected/             # Independent geometric and rubric evaluators
│   ├── fixtures/             # Official problem statement PDF & reference report
│   ├── regressions/          # REG-001 through REG-012 permanent test suite
│   └── run_hackathon_mission.py # Autonomous Hackathon 2026 mission runner
├── docs/                     # Documentation and live UI screenshot evidence
└── pyproject.toml            # Project configuration and dependencies
```

---

## 6. License
Apache-2.0 License. Developed for SkyTrack Mission Studio.
