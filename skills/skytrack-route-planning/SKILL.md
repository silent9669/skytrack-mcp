---
name: skytrack-route-planning
description: Designs optimal 3D flight trajectories, coverage sweeps, and obstacle-avoidance corridors with static collision verification.
---

# SkyTrack Route Planning Skill

## Purpose
Translates mission locations and survey polygons into optimal 3D trajectories. Integrates the SkyTrack Path Planner API (`:20007`) for coverage sweeps and uses 3D Slab-method collision detection to guarantee that all flight legs maintain required clearance from physical structures.

## Trigger Conditions
- Triggered when creating a new route, planning a survey, or repairing a colliding trajectory.

## Relevant MCP Tools
- `plan_coverage_route(area_coords, spacing_m, orientation_deg, altitude_m, hole_coords, no_fly_zones)`
- `check_route_collisions(world_name, waypoints, clearance_m)`
- `tool_skytrack_validate_mission(mission_id)`

## Planning Procedure
1. **Determine Route Topology:**
   - *Point-to-point / Patrol:* Construct waypoint sequence through target locations.
   - *Area Survey / Lawnmower:* Use `plan_coverage_route` to generate parallel sweeps across the bounding polygon.
2. **Altitude Assignment:** Set flight altitude above static low structures (e.g. 3.5m in warehouse to clear 2.83m racks).
3. **Insert Corridor Anchors:** If a straight line intersects an obstacle (e.g. a pillar or wall corner), insert intermediate dogleg waypoints to route through open free space.
4. **Attach Waypoint Actions:** Attach `drop-ball`, `take-snapshot`, or video triggers at relevant waypoint indices.
5. **Verify 3D Collision Freedom:**
   - Execute `check_route_collisions(world_name, waypoints, clearance_m=0.4)`.
   - If conflicts exist, inspect `conflicts` list, note the intersecting obstacle AABB, adjust coordinates, and re-test until `is_collision_free == True`.
6. **Return Home Strategy:** Ensure final leg returns to spawn location (`[0,0,altitude]`) before initiating landing or RTL.
