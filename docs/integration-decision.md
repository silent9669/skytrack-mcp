# SkyTrack Integration Decision Matrix

## Decision Philosophy
Following Section 3 of the goal specification:
1. Highest priority to structured interfaces (APIs, SDKs, JSON formats, Docker, Gazebo SDF).
2. Avoid fragile hard-coded mouse clicks or coordinate-only automation.
3. Fall back to Computer Use (screencapture, focus, keyboard) only for visual verification, modal dismissal, or when structured access is insufficient.

## Interface Matrix

| Capability | Integration Surface | Latency | Reliability | Maintainability | Selected? | Rationale |
|---|---|---|---|---|---|---|
| **Mission Storage** | Local JSON files (`plan.json`, `mission.json`) | ~1ms | Very High | High | **YES** | Allows direct manipulation of waypoints without UI lag or coordinate drift; immediately reflects on UI. |
| **Cloud Mission Sync** | SkyTrack Cloud BFF API (`platform.getskytrack.com`) | ~300ms | High | High | **YES** | Solves the "0 missions" issue by registering missions on the cloud backend with decrypted auth cookies. |
| **Coverage Route Planning** | Path Planner REST API (`:20007/plan-coverage-xy`) | ~20ms | Very High | High | **YES** | Native Boustrophedon path optimization algorithm built into SkyTrack daemon; handles NFZ splits. |
| **Mission Execution** | GCS Control API (`:20002/mission/v2/execute`) | ~15ms | Very High | High | **YES** | Canonical execution endpoint; natively converts frontend ENU actions to onboard NED commands. |
| **Direct Flight Control** | GCS Control API (`:20002/flight/v2/...`) | ~10ms | Very High | High | **YES** | Direct, deterministic endpoints for Takeoff, Land, and RTL. |
| **Live Telemetry** | MAVLink Bridge (`ws://127.0.0.1:9005`) | ~100ms | Very High | Medium | **YES** | Exposes armed state, landed state, battery, heading, Euler attitude, and GPS position at 10 Hz. |
| **3D World Inspection** | Gazebo `.sdf` XML Parser | ~5ms | Very High | High | **YES** | Exact physical geometries, bounding boxes, and collision shapes extracted mathematically without visual guessing. |
| **Collision Checking** | 3D Slab Intersection Math | <1ms | Very High | High | **YES** | Deterministic geometric verification ensuring flight legs never intersect obstacle bounding boxes. |
| **Python Autonomy** | Docker `exec` + `cp` into ROS 2 `skytrack-autonomy` | ~1s | High | Medium | **YES** | Runs production `local_planner` scripts inside the container with ROS 2 Jazzy. |
| **Window & UI Control** | macOS AppleScript & Screencapture | ~50ms | Medium | Medium | **FALLBACK** | Used for window focus, modal dialog dismissal (Escape), and screenshot capture. |
| **Mouse Click Automation** | Absolute Screen Coordinates | ~200ms | Low | Poor | **NO** | Strongly rejected per Section 3; fragile across DPI, resolution, and window position changes. |
