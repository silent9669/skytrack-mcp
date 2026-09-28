---
name: skytrack-operator
description: Orchestrate SkyTrack Mission Studio requests with exact target resolution, authorization checks, safe authoring, evidence-based debugging, and user-run simulation handoff.
---

# SkyTrack Operator Skill

## Purpose and triggers

Use for any natural-language request about SkyTrack Mission Studio: inspect or explain a mission, plan a route, author or repair a mission, debug a run, or verify evidence. `/skytrack` is an optional invocation when available; do not require it. A request to inspect, review, explain, or analyze is read-only unless the user explicitly asks for a change.

## Required target and permission gates

1. Resolve the user's project and mission names or IDs with `tool_skytrack_resolve_target`. Continue only with an unambiguous exact `(project_id, mission_id)` pair. Do not infer a target from the active mission, recency, or a partial name. If the mission is missing, ask the user before creating it; if the result is ambiguous or unavailable, ask for clarification or restore access.
2. Before any requested edit or repair, call `tool_skytrack_check_permission` for that exact pair. Edit only when `edit_authorization` is `VERIFIED` and `read_only_enforced` is false. Treat `DENIED` and `UNVERIFIED` as read-only outcomes. Do not bypass a view-only role or an immutable, locked, judge, or submission snapshot by cloning, switching accounts, or writing files directly.
3. Carry the exact pair through every stage. Pass `project_id` and `mission_id` to tools that accept them; where only `mission_id` is accepted, verify the result still names the resolved mission and project before continuing.

## Normal workflow

1. **Classify intent:** distinguish read-only inspection/review from an explicit author, repair, or debug request. Load the task-understanding playbook for a new assignment.
2. **Inspect context:** read the exact mission and its Plan and Code representations before authoring. Load the world/route playbooks only when route constraints matter. Check the selected vehicle's payload and mission coordinate frame, altitude, collision and geometry constraints for any planned route.
3. **Authorize changes:** for any edit, run the permission check immediately before editing. If authorization is denied or unverified, stop at diagnosis or proposal.
4. **Author safely:** use Plan Mode for waypoint and payload-action missions; prefer Code Mode for dynamic perception, AI/model inference, or tasks requiring autonomy SDK logic. Preserve the inactive representation when changing modes. Save through the transactional/snapshot-backed authoring path; read back the exact mission, both representations, and mode, then run static validation. If safe transactional persistence is unavailable, do not fall back to direct file writes.
5. **Hand off simulation:** all simulations are run by the user in SkyTrack Desktop, using Local Docker or Cloud. The agent NEVER dispatches, executes, starts, stops, restarts, or controls a flight or simulation. Give the user the exact mission IDs and validation/read-back result so they can run it themselves.
6. **Report evidence:** distinguish authored/validated state from a run. Do not claim flight success without native execution evidence tied to the exact mission and execution.

## Explicit debug workflow

When the user says “hãy debug” or asks to debug a failed run:

1. Resolve the exact project and mission pair. Inspect the latest run/report for that exact mission with `tool_skytrack_report_read(mission_id=<exact mission_id>)`; use the user-provided execution ID when available. Never inspect another mission's latest run as a substitute.
2. If there is no report tied to that mission, ask the user for the relevant logs, screenshots, video, or other media. Use user-provided evidence only when its mission/run provenance is clear; do not infer a failure from a planned route or unrelated container logs.
3. Diagnose the failure and state the evidence behind the diagnosis. Before repairing, call `tool_skytrack_check_permission` again for the same exact IDs. If verified and not read-only, make a targeted fix to that same mission, save transactionally, read both representations back, and run static validation. Otherwise provide the diagnosis without editing.
4. Hand the repaired and validated mission back to the user for rerun in SkyTrack Desktop. The agent does not execute that rerun.

## Evidence and stop conditions

- A saved mission and successful static validation prove authored state only, not a flight.
- When analyzing flight evidence, require a native report bound to both the exact mission and execution, with observed events and a terminal outcome relevant to the request. Mark missing evidence **unverified**.
- Stop before any write when target identity, permission, snapshot mutability, or transactional persistence is uncertain.
- Finish with what was inspected, what changed, validation/read-back evidence, the user action needed for rerun, and any remaining unverified claims.
