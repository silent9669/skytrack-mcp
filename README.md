# SkyTrack MCP Server 0.2.0

A cross-platform Model Context Protocol (MCP) server and Claude Code plugin for **SkyTrack Mission Studio**.

AI agents can inspect SkyTrack projects and worlds, safely author and validate missions as visual Plans or ROS 2 Python autonomy scripts, and analyze mission-bound reports. The agent resolves exact project/mission IDs and checks edit permission before writes. **The user runs every simulation in SkyTrack Desktop (Local Docker or Cloud); the agent never dispatches or controls flights.**

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code / OpenCode / Codex / other MCP host              │
│  Natural-language skill discovery + optional slash command   │
└──────────────────────────────┬───────────────────────────────┘
                               │ MCP stdio (JSON-RPC)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     SkyTrack MCP Server                      │
│  • Exact project/mission target resolution                   │
│  • Verified edit-permission checks; read-only when uncertain │
│  • Plan and Code authoring with snapshot-backed persistence   │
│  • Mission read-back, static validation, world/route checks  │
│  • Mission-bound report reading and requirement analysis     │
└───────────────────────┬──────────────────────────────────────┘
                        │ inspect / authorize / author / analyze
                        ▼
┌──────────────────────────────────────────────────────────────┐
│              SkyTrack Desktop & Cloud                        │
│  Projects, missions, ClientData, reports, and mission views   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ User-run simulation in SkyTrack Desktop                      │
│ Local Docker or Cloud — agent does not dispatch or control it │
└──────────────────────────────────────────────────────────────┘
```

Version 0.2.0 packages the server with a Claude Code plugin and operational skills. Mission changes are target- and permission-gated, saved with a recoverable transaction/snapshot path, read back, and statically checked. A saved or validated route is not flight evidence.

---

## 2. Installation & Setup

### Prerequisites
- macOS / Linux
- Python 3.10+ (Python 3.12 recommended)
- [uv](https://github.com/astral-sh/uv) or `pip`
- Docker Desktop (for SkyTrack simulation stack)

### Clone & Install
```bash
git clone https://github.com/silent9669/skytrack-mcp.git
cd skytrack-mcp

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Verify Installation
```bash
# Run offline unit, regression, and benchmark tests
pytest -v -m "not live_simulation"

# With the SkyTrack Docker stack running, run the environment-dependent checks
pytest -v -m live_simulation

# Score a synthetic Urban Fire Rescue dry-run (not native flight evidence)
python evals/run_hackathon_mission.py
# Live simulation attempts are user-run in SkyTrack Desktop; the agent never dispatches flights
```

### Install the Claude Code plugin globally (user scope)

The repository contains a Claude Code plugin manifest, SkyTrack skills, and a portable stdio MCP configuration. Clone the release into Claude Code's user-scope skills directory; Claude Code discovers plugin directories there without a separate install command:

```bash
mkdir -p ~/.claude/skills
git clone --branch v0.2.0 --depth 1 \
  https://github.com/silent9669/skytrack-mcp.git \
  ~/.claude/skills/skytrack
```

Start a new Claude Code session (or run `/reload-plugins` in an existing session). The plugin is available across projects on this machine; its naturally discoverable skill handles SkyTrack requests, and `/skytrack` is an optional shortcut when the repository skill is in scope. The MCP server starts with `uv run skytrack-mcp` from the plugin root. To update, fetch and check out a newer release tag in `~/.claude/skills/skytrack`.

### Configure OpenCode (user scope)

On macOS and Linux, put the following in `~/.config/opencode/opencode.json`. Replace the `cwd` placeholder with the absolute path to your SkyTrack MCP checkout (the same path format works on either OS):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "skytrack": {
      "type": "local",
      "command": ["uv", "run", "skytrack-mcp"],
      "cwd": "/absolute/path/to/skytrack-mcp",
      "enabled": true
    }
  }
}
```

### Configure Codex (user scope)

On macOS and Linux, add this to `~/.codex/config.toml`, replacing the `cwd` placeholder with the absolute path to your SkyTrack MCP checkout:

```toml
[mcp_servers.skytrack]
command = "uv"
args = ["run", "skytrack-mcp"]
cwd = "/absolute/path/to/skytrack-mcp"
```

These direct stdio configurations require `uv` and Python 3.10 or newer. In every host, the agent authors, saves, reads back, and validates the mission; the user launches simulations in SkyTrack Desktop using Local Docker or Cloud. Reviewing or debugging a report does not start a flight.

### Configure Claude Desktop (optional)

For Claude Desktop, use the installed console script's absolute path in `claude_desktop_config.json`:

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
- **Simulation boundary:** The user runs simulations in SkyTrack Desktop (Local Docker or Cloud). The agent must not dispatch, start, stop, restart, or control flights.
- **Verification & Reports:** `harvest_flight_report`, `tool_skytrack_report_read`, `tool_skytrack_verify_mission_requirements`, `validate_uav_python_code`

---

## 5. Repository Structure

```
skytrack-mcp/
├── src/skytrack_mcp/         # MCP server, autonomy SDK, simulation & clients
├── .claude-plugin/           # Global Claude Code plugin manifest
├── .claude/skills/skytrack/  # Discoverable SkyTrack skill / optional slash shortcut
├── skills/                   # Agent operational playbooks (10 internal guides)
├── tests/                    # Pytest unit, integration, and benchmark tests
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
