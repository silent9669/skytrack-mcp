---
name: skytrack-mission-authoring
description: Author or repair SkyTrack missions in Plan or Code Mode with exact-target authorization, safe mode switching, transactional persistence, read-back, and static validation.
---

# SkyTrack Mission Authoring

## Scope

This playbook is for explicit user requests to create or edit a mission. Review, explanation, and inspection requests are read-only. The user runs all simulations in SkyTrack Desktop (Local Docker or Cloud); the agent NEVER dispatches, executes, or controls flights.

## Target and authorization gate

1. Call `tool_skytrack_resolve_target` with the project and mission names or IDs. Continue only with the exact, unambiguous `(project_id, mission_id)` result. Do not infer the active or most-recent mission. If the mission is missing, ask before creating it; clarify ambiguous or unavailable targets.
2. Read the target's existing Plan and Code representations and mode before any edit.
3. Call `tool_skytrack_check_permission` with the exact resolved project and mission IDs immediately before authoring. Edit only if `edit_authorization` is `VERIFIED` and `read_only_enforced` is false. `DENIED` or `UNVERIFIED` means stop at read-only diagnosis or proposal. Never modify a view-only project or immutable, locked, judge, or submission snapshot, and do not work around a lock by cloning or writing directly to files.

## Choose the representation

- **Plan Mode** is the default for waypoint routes, coverage, and discrete payload actions such as snapshots or video start/stop.
- **Code Mode** is preferred for dynamic perception, AI/model inference, conditional mission logic, or features that need the SkyTrack autonomy SDK. Use the verified SDK reference/template for the required level.
- Inspect both representations first. A mode change must preserve the inactive representation byte-for-byte/semantically intact; never clear or regenerate the inactive Plan or Code representation as a side effect. If a tool cannot safely preserve it, stop and ask rather than switching.

## Transactional author-save-readback loop

1. Make only the requested, targeted change on the exact authorized mission. Keep the existing coordinate frame, world, vehicle, and unrelated actions unless the request explicitly changes them.
2. Use the transactional/snapshot-backed mission save path for the selected representation. For canonical Plan/metadata patches, use the atomic, snapshot-backed mission patch tool when it supports the requested fields. For Code Mode, use `write_and_save_uav_script` to AST-validate and save, with the explicit target mission ID and safe mode switch option. If the available path cannot provide a recoverable transaction or preserve the inactive representation, do not use a direct file write as a substitute.
3. Check the save result and returned target IDs. Then read the exact mission back with `tool_skytrack_get_mission` (and raw mission state if needed). Verify the intended Plan/Code content, active mode, unchanged inactive representation, and that the returned project/mission pair matches the target.
4. Run `tool_skytrack_validate_mission` after persistence. For routes, also perform the needed world/collision and vehicle constraint checks; unresolved geometry remains unknown, not collision-free. Report any failed or unavailable check explicitly.
5. Hand off the saved, read-back, validated mission to the user. Do not run or dispatch it.

## Explicit debug repair

When the user says “hãy debug” or asks to debug a run, first inspect the latest report/run of the exact resolved mission with `tool_skytrack_report_read(mission_id=<exact mission_id>)`; use an execution ID supplied by the user when they provide one. If the mission-bound report is unavailable, ask for user-provided logs, screenshots, video, or other media with clear run provenance. Do not infer a root cause from a plan, or substitute another mission's latest run. Diagnose from evidence, recheck edit permission, and if verified make a targeted repair to that same mission through the transactional loop above. Then hand off to the user for a rerun in SkyTrack Desktop. The agent never executes the rerun.

## Tool references

- Target and permission: `tool_skytrack_resolve_target`, `tool_skytrack_check_permission`
- Read/save/validate: `tool_skytrack_get_mission`, `tool_skytrack_get_mission_json`, `tool_skytrack_patch_mission`, `tool_skytrack_save_mission`, `write_and_save_uav_script`, `tool_skytrack_validate_mission`
- Planning context: `tool_skytrack_inspect_world`, `tool_skytrack_get_vehicle_context`, `check_route_collisions`, `get_uav_python_sdk_reference`
- Debug evidence: `tool_skytrack_report_read`, `tool_skytrack_logs`; user-supplied media remains the user's evidence
