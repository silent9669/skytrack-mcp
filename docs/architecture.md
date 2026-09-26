# SkyTrack MCP Integration Architecture

## 1. Multi-Layer Design

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Autonomous AI Agent (Claude Code)                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Model Context Protocol (stdio)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        SkyTrack MCP Server Layer                       │
│  - 45+ Tools grouped by capability (Environment, Mission, World, ...)  │
│  - 8 Managed Resources (skytrack://...)                                │
│  - 5 Workflow Prompts                                                  │
└───────┬──────────────┬──────────────┬──────────────┬────────────┬──────┘
        │              │              │              │            │
        ▼              ▼              ▼              ▼            ▼
┌──────────────┐┌──────────────┐┌─────────────┐┌───────────┐┌────────────┐
│   Adapters   ││   Mission    ││    World    ││   Route   ││ Simulation │
│  - Cloud BFF ││  - Canonical ││ - SDF Parser││- Geometry ││- Lifecycle │
│  - Storage   ││  - Validator ││ - 3D AABB   ││- Coverage ││- Runner    │
│  - GCS API   ││  - Patcher   ││ - 2D Grid   ││- NFZ Split││- Observer  │
│  - Docker    ││  - Parser    ││             ││           ││- Telemetry │
└──────────────┘└──────────────┘└─────────────┘└───────────┘└────────────┘
        │              │              │              │            │
        ▼              ▼              ▼              ▼            ▼
┌────────────────────────────────────────────────────────────────────────┐
│                Physical Machine & Container Runtime                    │
│  - Electron ClientData: prj-... / mis-... / plan.json / script.py      │
│  - SkyTrack Cloud BFF API: https://platform.getskytrack.com            │
│  - GCS Backend (:20002) & Path Planner (:20007)                        │
│  - Gazebo Harmonic (:20005) & PX4 SITL                                 │
│  - Mission Edge Computer & ROS 2 Autonomy (local_planner SDK)          │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. Core Subsystems

### A. Adapter Layer (`src/skytrack_mcp/adapters/` and `clients/`)
- **Cloud Client:** Decrypts AES-256 tokens using the macOS hardware UUID and calls the SkyTrack Cloud API to list projects, create missions, and sync metadata.
- **Storage Sync:** Manages local mission folders, visual sequences in `plan.json`, metadata in `mission.json`, and Python scripts in `script.py`.
- **GCS & Planner Client:** HTTP/WebSocket client communicating with FastAPI endpoints on ports `:20002` (UAV Control) and `:20007` (Path Planner).
- **Docker Client:** Controls containers, checks status, injects scripts, and reads logs.

### B. Mission Layer (`src/skytrack_mcp/mission/`)
- **Canonical Model:** Pydantic-based representation (`CanonicalMission`, `Waypoint`, `ValidationIssue`) decoupling business logic from storage schemas.
- **Validator:** Static pre-flight rules checking altitudes (1.0m - 50.0m), speeds (0.5m/s - 12.0m/s), payload capacities (e.g. max 5 balls), sensor-vehicle compatibility, and sequence integrity.
- **Patcher:** Snapshot-backed transactional modification engine with automated rollback.

### C. World & Route Analysis (`src/skytrack_mcp/world/` & `route/`)
- **SDF Engine:** Parses Gazebo XML, extracts 3D collision bounding boxes, and generates 2D top-down ASCII occupancy grids at flight altitude.
- **Collision Checker:** Tests 3D segments against inflated obstacle bounding boxes using the Slab method.
- **Coverage Planner:** Calls the Path Planner API for Boustrophedon sweeps and splits legs crossing No-Fly Zones.

### D. Simulation & Reporting (`src/skytrack_mcp/simulation/` & `report/`)
- **Lifecycle Engine:** Boots and configures `docker-compose` stacks with custom worlds, vehicle models, and spawn locations.
- **Observer:** Asynchronous polling loop tracking vehicle liftoff, cruise, and touchdown.
- **Report Harvester & Verification:** Compiles `flight_report.json` and evaluates requirement verification matrices (PASS / FAIL / UNKNOWN).
