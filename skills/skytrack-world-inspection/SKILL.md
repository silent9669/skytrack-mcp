---
name: skytrack-world-inspection
description: Analyzes 3D Gazebo environment geometry, static obstacle bounding boxes, spawn positions, and 2D occupancy grid slices.
---

# SkyTrack World Inspection Skill

## Purpose
Enables an autonomous agent to understand the physical reality of the target 3D world before placing a single waypoint. Extracts physical obstacles (walls, racks, poles, terrain structures) from Gazebo `.sdf` files and generates 2D top-down ASCII occupancy grids at the proposed flight altitude.

## Trigger Conditions
- Triggered whenever a mission requires operating in a new or uninspected world.
- Triggered when collision checks fail and alternate corridors must be identified.

## Relevant MCP Tools
- `tool_skytrack_inspect_world(world_name, slice_altitude_m, grid_half_size_m, grid_resolution)`
- `tool_skytrack_get_world_context(world_name)`
- `tool_skytrack_capture_world()`

## Inspection Procedure
1. **Query World Context:** Fetch spherical coordinates (lat, lon, elevation) and total model counts.
2. **Inspect Slices at Multi-Altitudes:**
   - Low Altitude (1.5m): Inspect ground racks, pallets, vehicles, control panels.
   - Cruise Altitude (3.0m - 5.0m): Inspect tall storage racks, building walls, support pillars.
   - High Altitude (10.0m+): Inspect crane towers, factory ceilings, power lines.
3. **Analyze 2D ASCII Grid:**
   - Identify origin `S` (spawn point `[0,0]`).
   - Identify obstacle corridors indicated by `#` boundaries.
   - Locate free-flight channels indicated by `.` markers.
4. **Identify Safety Anchor Points:** Select waypoint coordinates situated at least 0.5m away from any `#` block.

## Example Output Interpretation
In `warehouse.sdf`:
- `workcell.rack1` to `rack5` are standard warehouse shelving units (height 2.83m).
- `workcell.pole1`, `pole2`, `pole3` are vertical support pillars (height 6.04m, center Y ≈ -2.34m).
- Safe lateral corridor: X ≈ 2.6m to 7.3m, with waypoints routing between pillars.
