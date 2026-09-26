# SkyTrack Research and Environment Discovery

## 1. System Environment
- **Host OS:** macOS 27.0 (Darwin arm64)
- **Application Bundle:** `/Applications/SkyTrack.app`
- **Application Type:** Electron 39.8.10 with Node.js 22 runtime and Chromium
- **SkyTrack Client Version:** `1.2.2` (CFBundleShortVersionString: 1.2.2, internal package name: `skytrack-client`)
- **Bundle Integrity:** `Resources/app.asar` SHA-256 verified

## 2. Process Architecture
When SkyTrack Mission Studio is active, it coordinates processes across macOS and Docker Desktop:
- **macOS Processes:**
  * Main Process: `/Applications/SkyTrack.app/Contents/MacOS/SkyTrack`
  * Renderer Process: `SkyTrack Helper (Renderer)` (loads `dist/renderer/index.html` with React/Vite UI bundle)
  * GPU Helper: `SkyTrack Helper (GPU)`
  * Network Service: `SkyTrack Helper`
  * Express Local Storage Server: Port `20080` (serves cache and assets)
  * Local Update Server: Port `20081`
  * Cloud Sim Proxy: Port `20082`

- **Docker Simulation Stack (7 Containers on `skytrack-network` bridge 172.254.0.0/16):**
  1. `skytrack-simulation-gazebo-1` (`172.254.0.12`, port `:20005`): Gazebo Harmonic 8.15.0 headless physics & sensor simulation.
  2. `skytrack-simulation-px4-1` (`172.254.0.2`): PX4 Autopilot SITL (`sys_autostart: 4001`), communicates with Gazebo via gz-transport (`GZ_RELAY=172.254.0.12`).
  3. `skytrack-simulation-mission-computer-1` (`172.254.0.3`): ROS 2 Jazzy running edge mission nodes (`actions_node`, `mission_node`, `ball_dropper`, `spray_trigger`, `gimbal_control`).
  4. `skytrack-simulation-skytrack-autonomy-1` (`172.254.0.14`): ROS 2 Jazzy container running Python autonomy scripts via `local_planner` SDK.
  5. `skytrack-deamon-gcs-backend-1` (`172.254.0.6`, ports `:20002` and `:20007`): UAV Control API (`:20002`) and SkyTrack Path Planner API (`:20007`).
  6. `skytrack-deamon-mavlink-bridge-1` (`172.254.0.9`, internal port `9005`): MAVSDK/MAVLink telemetry bridge streaming high-frequency state.
  7. `skytrack-deamon-websocket-proxy-1` (`172.254.0.11`, port `:20443`): Nginx reverse proxy with mTLS.

## 3. Storage and State Layout
- **Path:** `~/Library/Application Support/SkyTrack/ClientData`
- **Projects & Missions:** Stored in `prj-<project_id>/mis-<mission_id>/`:
  * `mission.json`: World name, vehicle model, takeoff altitude, target speed, safety options, end behavior (RTL/Land), and `codeMode` toggle.
  * `plan.json`: Visual waypoint sequences, spawn location, and actions (`navigate`, `drop-ball`, `take-snapshot`, `start-recording-video`, etc.).
  * `script.py`: Python UAV script for autonomous ROS 2 execution.
  * `media/`: Captures (`captures/`) and video recordings (`recordings/`).
  * `logs/`: PX4 `.ulg` logs and scan reports.
- **Authentication & Cloud State:**
  * `.token` and `.csrf`: Encrypted using AES-256-CBC with double SHA-256 derived from hardware `IOPlatformUUID`.
  * Cloud API: `https://platform.getskytrack.com/api/v1/projects` and `/api/v1/user/missions`.
