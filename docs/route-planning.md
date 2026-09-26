# SkyTrack Route Planning & Geometry

## 1. Planning Paradigms

1. **Deterministic Boustrophedon Coverage (Lawnmower):**
   - Utilizes SkyTrack Path Planner API (`POST 127.0.0.1:20007/plan-coverage-xy`).
   - Generates parallel sweep corridors based on camera field of view, altitude, and overlap.
   - Automatically cuts legs around No-Fly Zones using `/split-waypoints-nfz`.

2. **Obstacle-Aware Corridor Routing:**
   - Navigates through complex indoor or structured worlds (such as `warehouse`, `factory`, `city`).
   - Waypoints are placed along clear corridors identified through 2D occupancy slices.

## 2. Route Metrics Computation
For every candidate trajectory, the MCP calculates:
- Total 3D distance (meters).
- Total 2D planar distance (meters).
- Altitude profile (minimum and maximum altitude).
- Estimated flight duration:
  $$T_{\text{est}} = \frac{D_{\text{3D}}}{v_{\text{target}}}$$

## 3. Waypoint Action Attachments
Actions in SkyTrack are attached directly to waypoints:
- `drop-ball`: Attached after waypoint navigation to trigger payload release.
- `take-snapshot`: Attached to capture camera still image upon arrival.
- `start-recording-video` / `stop-recording-video`: Delimits continuous survey areas.
