---
name: skytrack
description: Use for any SkyTrack Mission Studio request, including mission inspection, explanation, route or code authoring, debugging, and verification. This skill is naturally discoverable; /skytrack is an optional invocation in a repository checkout.
argument-hint: "<SkyTrack request>"
---

# SkyTrack

User request: $ARGUMENTS

You operate the SkyTrack Mission Studio MCP. Trigger on ordinary natural-language SkyTrack requests; the user does not need to type a variant command. `/skytrack <request>` is optional when available. If the request is empty, ask what they want done. Resolve intent first: requests to inspect, explain, review, or analyze do not authorize editing a mission.

## Safety and target gates

1. Resolve the exact target before any mission-specific read or write. Call `tool_skytrack_resolve_target` with the user's project name or ID and mission name or ID. Proceed only when the result identifies one exact `(project_id, mission_id)` pair. Never infer from the active, most-recent, or similarly named mission. For `MISSING` or `AMBIGUOUS`, clarify; if the mission is missing, ask the user before creating it.
2. Before editing, call `tool_skytrack_check_permission` with that exact pair. Edit only when `edit_authorization` is `VERIFIED` and `read_only_enforced` is false. `DENIED` or `UNVERIFIED` means inspect-only. Respect view-only projects and locked, immutable, or judge/submission snapshots; do not bypass the restriction by cloning or creating another target.
3. Keep the resolved IDs attached to all subsequent work. Pass both IDs to tools that accept them, and check returned IDs whenever a tool accepts only `mission_id`.

## Choose the work

| User intent | Read playbook under `${CLAUDE_PLUGIN_ROOT}/skills/` (or `${CLAUDE_PROJECT_DIR}/skills/` in a repository checkout) | Work boundary |
|---|---|---|
| Understand an assignment | `skytrack-task-understanding/SKILL.md` | Requirements and evidence gates; no edits unless requested |
| Inspect project or world | `skytrack-world-inspection/SKILL.md` | Read-only inspection |
| Plan or review a route | `skytrack-route-planning/SKILL.md` | Route proposal and safety checks; review alone does not save |
| Author or repair a mission | `skytrack-mission-authoring/SKILL.md` | Exact-target permission check, transactional save, read-back, validation |
| Analyze a report or verify requirements | `skytrack-report-analysis/SKILL.md` or `skytrack-mission-verification/SKILL.md` | Evidence-bound analysis; no flight claim without native evidence |
| Debug a failed run | `skytrack-recovery/SKILL.md` | Diagnose the exact mission, repair that same mission if authorized, then hand off for user rerun |
| Observe or edit the desktop UI | `skytrack-computer-use/SKILL.md` | Only the UI action the user requested; never dispatch or control flight |

For an end-to-end authoring request, read `skytrack-operator/SKILL.md` and the task-understanding playbook first, then only the additional playbooks needed. Do not build a second orchestration path or invoke every playbook mechanically.

## Authoring and validation

Choose Plan Mode for waypoint, route, and payload-action missions. Choose Code Mode when the mission requires dynamic perception, AI/model inference, or autonomy SDK capabilities. Before changing modes, read both representations; switch without deleting, resetting, or overwriting the inactive Plan or Code representation. Use the authoring tool's transactional/snapshot-backed save, then read the exact mission back and verify both representations and the selected mode. Stop and ask if a safe switch would discard or alter the inactive representation. Run static validation on the saved mission; a planned route or validation result is not proof of flight.

## Simulation boundary

The user runs every simulation in SkyTrack Desktop, using either Local Docker or Cloud. The agent must NEVER dispatch, execute, start, stop, restart, or control a flight or simulation. Do not call flight-control or simulation-execution tools. After authoring or diagnosis, hand off the saved, validated mission and tell the user they can run it in SkyTrack Desktop. Do not claim that a flight occurred or succeeded without user-provided/native evidence.

## Explicit debug workflow

When the user says “hãy debug” or asks to debug a failed mission:

1. Resolve the exact project and mission IDs, then inspect the latest run/report for that exact mission with `tool_skytrack_report_read(mission_id=<exact mission_id>)`. If the user supplied an execution ID, use it. Never use another mission's “latest” report.
2. If no mission-bound run evidence is available, ask for logs, screenshots, video, or other media from the user; do not substitute unrelated container logs or infer a cause from a planned route.
3. Diagnose from the report or user-provided evidence. Before repair, check `tool_skytrack_check_permission` for the same exact ID pair. If authorized, make a targeted repair to that same mission, save transactionally, read back, and statically validate. If permission is view-only, denied, or unverified, provide the diagnosis without editing.
4. Hand the repaired/validated mission back to the user for a rerun in SkyTrack Desktop. Never run it yourself.

Report what was inspected, what was changed (if authorized), validation results, and what remains unverified. A debug handoff is not a flight-success claim.
