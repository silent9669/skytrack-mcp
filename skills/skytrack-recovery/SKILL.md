---
name: skytrack-recovery
description: Diagnoses runtime failures, unfreezes blocked simulations, repairs invalid routes, and self-heals the SkyTrack environment.
---

# SkyTrack Recovery Skill

## Purpose
Provides deterministic fault-handling and automated recovery procedures when SkyTrack, Docker containers, PX4, or ROS 2 user scripts encounter unexpected errors, timeouts, modal blocks, or stuck simulation loops.

## Trigger Conditions
- Triggered when `tool_skytrack_healthcheck` reports failures.
- Triggered when flight polling times out or fails to detect liftoff.
- Triggered when static validation reports errors on an imported mission.
- Triggered when the SkyTrack UI becomes unresponsive.

## Relevant MCP Tools
- `tool_skytrack_recover(issue_type)`
- `tool_skytrack_diagnostics()`
- `tool_skytrack_logs()`
- `tool_skytrack_patch_mission(patches)`
- `stop_uav_python_script()`
- `tool_skytrack_simulation_restart()`

## Standard Recovery Runbooks

### 1. Docker Simulation Stack Stuck or Frozen
- **Symptom:** Containers running but GCS API `:20002` or Gazebo `:20005` times out.
- **Runbook:**
  1. Call `tool_skytrack_recover(issue_type="docker")`.
  2. If still unhealthy, execute `tool_skytrack_simulation_stop()`, wait 2 seconds, and execute `tool_skytrack_simulation_start()`.

### 2. Orphaned Python Script in Autonomy Container
- **Symptom:** Starting a new mission script fails because a previous `user-script.py` holds ROS 2 locks.
- **Runbook:**
  1. Call `stop_uav_python_script()`.
  2. Verify with `tool_skytrack_logs()` that the process terminated cleanly.

### 3. Waypoint Collision or Out-of-Bounds Error
- **Symptom:** Static validation or 3D collision check reports `is_collision_free == False`.
- **Runbook:**
  1. Inspect the `conflicts` list to identify obstacle bounding box coordinates.
  2. If the collision is with a floor/rack: increase waypoint altitude by +0.5m.
  3. If the collision is with a vertical pillar/wall: add an intermediate dogleg waypoint shifted laterally away from the obstacle center.
  4. Apply patch via `tool_skytrack_patch_mission()` and re-validate.

### 4. SkyTrack Desktop Lost Window Focus or Blocked by Modal Dialog
- **Symptom:** Screenshot shows an unclosed popup, or keystrokes are ignored.
- **Runbook:**
  1. Call `tool_skytrack_focus()`.
  2. Send `tool_ui_key("escape")` twice to dismiss any open modal dialogs.
