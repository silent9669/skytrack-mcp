# SkyTrack Simulation Lifecycle & Control

## 1. Multi-Container Orchestration
The SkyTrack simulation environment consists of 7 Docker containers operating over `skytrack-network` (`172.254.0.0/16`):
- `skytrack-simulation-gazebo-1`: 3D physics and sensor simulation.
- `skytrack-simulation-px4-1`: PX4 Autopilot SITL flight controller.
- `skytrack-simulation-mission-computer-1`: ROS 2 Jazzy edge nodes.
- `skytrack-simulation-skytrack-autonomy-1`: Python autonomy runtime (`local_planner`).
- `skytrack-deamon-gcs-backend-1`: Control and Path Planner APIs.
- `skytrack-deamon-mavlink-bridge-1`: Real-time MAVLink telemetry bridge.
- `skytrack-deamon-websocket-proxy-1`: Secure WebSocket proxy.

## 2. Execution Methods

1. **GCS Control API Execution (`POST :20002/mission/v2/execute`):**
   - Transmits complete mission JSON payload.
   - GCS converts ENU coordinates to NED wire format.
   - Handled directly by `actions_node` and `mission_node`.

2. **Python Container Execution (`skytrack-autonomy`):**
   - Deploys Python script to `/app/local_planner/.../user-script.py`.
   - Executes inside container:
     ```bash
     source /opt/ros/jazzy/setup.bash && source /app/setup.sh && python3 -u user-script.py
     ```
   - Managed via `execute_uav_python_script` and `stop_uav_python_script`.

## 3. Real-Time Telemetry & Observation Loop
The observer loop polls the MAVLink WebSocket (`ws://127.0.0.1:9005`) and tracks:
- Armed status (`is_armed`: `True` / `False`).
- Landed state (`landed_state`: `ON_GROUND`, `TAKEOFF`, `IN_AIR`, `LANDING`).
- Flight mode (`flight_mode`: `HOLD`, `OFFBOARD`, `AUTO_RTL`, `AUTO_LAND`).
- Battery percentage.
- Local ENU position relative to home origin.
- Confirms touchdown when state returns to `ON_GROUND` after an `IN_AIR` phase.
