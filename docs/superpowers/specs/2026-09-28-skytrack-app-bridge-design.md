# SkyTrack Mission Authoring and Ready-to-Run Handoff

**Date:** 2026-09-28  
**Status:** Superseded on 2026-09-28 by [`2026-09-28-skytrack-agent-workflow-design.md`](2026-09-28-skytrack-agent-workflow-design.md). Retained as historical context; do not implement as-is.

## Purpose

Enable Claude Code, through the locally hosted SkyTrack MCP, to target a specific SkyTrack mission, author either a visual Plan or Python Code mission using the supported autonomy SDK, validate and independently review the result, and hand it to the user as ready to execute in SkyTrack Mission Studio. Local execution, observation, logs, and reports may be used only through explicitly Local-only operations with appropriate authorization and safety checks. Cloud dispatch remains blocked until a supported Mission Studio bridge is available.

## User Outcome

The normal workflow is **understand → select exact mission/project → author → save → read back → validate → independent review → ready-for-user-to-execute**. Claude must not silently choose the most-recent mission, lose plan actions while editing, convert Code mode into Plan mode, equate AST validity with runnable code, or imply that a Cloud run occurred because metadata was synchronized.

The user may explicitly authorize a separate Local Docker simulation run. Otherwise, the default is to stop at the reviewed, ready-to-run handoff so the user can run the mission in SkyTrack.

## Current State

The MCP currently combines separate surfaces:

- Cloud project listing and mission create/update in `src/skytrack_mcp/clients/cloud_client.py`; Cloud authentication uses the local SkyTrack ClientData token cache.
- Visual mission files (`plan.json`, `mission.json`) and Python scripts (`script.py`) in local ClientData through `src/skytrack_mcp/clients/storage_sync.py`.
- Visual mission read/write and mission tools in `src/skytrack_mcp/server.py` and `src/skytrack_mcp/mcp/tools.py`.
- Static mission validation in `src/skytrack_mcp/mission/validator.py` and Python AST/SDK validation in `src/skytrack_mcp/autonomy_sdk.py`.
- Local visual dispatch through GCS, Python script execution in the autonomy Docker container, and local telemetry/log/report tools.
- Agent guidance through `.claude/skills/skytrack/SKILL.md`, `skills/skytrack-*/SKILL.md`, and MCP prompts/resources.

Focused review found these behavior gaps relevant to the intended authoring handoff:

- Write resolution can default to the most-recent local mission; new mission resolution has a hard-coded project fallback.
- Python save can swallow metadata-write errors and report Code mode requested without verifying persisted metadata.
- Plan parser/patcher round-trips through a reduced representation and can lose multiple or standalone actions, extra sequences, or metadata when patching.
- Mission validation can reject valid Code-only missions for having no visual waypoints; AST acceptance can overstate executability when required SDK entry points are missing.
- Cloud sync forces `codeMode=false` and omits the script, which can downgrade a Code mission.
- The `/skytrack` prompt path encourages execution rather than making reviewed handoff the default.
- Direct Local GCS/Docker execution does not follow Mission Studio's selected Local/Cloud setting. It is not Cloud dispatch.

No supported external Mission Studio runtime bridge is available in this repository. Installed-app Electron IPC and Cloud proxy details are private implementation observations, not a supported MCP contract, and must not be used as production endpoints.

## Goals

1. Require explicit project and mission identity for every mutation; never write to an inferred most-recent mission.
2. Preserve visual Plan data losslessly or reject an edit whose data shape cannot be safely preserved.
3. Save Plan and Code representations independently, surface write failures, and verify persisted content and `codeMode` by read-back.
4. Distinguish Code syntax/AST validation, known SDK API compatibility, mission-mode validity, runtime readiness, and actual execution evidence.
5. Use documented SDK reference material and Levels 1–6 templates for valid mission scripts; do not invent flight primitives.
6. Make an independent, read-only reviewer assess the requirements, exact saved artifact, validation outputs, and known limitations before returning a ready-to-run status.
7. Default the Claude Code `/skytrack` workflow to an author/validate/review/handoff, not a dispatch.
8. Keep existing direct execution and observation clearly Local Docker-only and opt-in; never use them for a Cloud-selected request.
9. Keep Cloud metadata synchronization separate from Cloud artifact persistence and Cloud execution. Never downgrade Code mode or claim Cloud readiness when the script was not preserved and verified.
10. Preserve existing native evidence and release-gating behavior outside changes strictly required for this authoring/readiness flow.

## Non-Goals

- Implementing or guessing an undocumented Mission Studio IPC, HTTP, URL-scheme, or Cloud proxy interface.
- Claiming that local ClientData persistence or Cloud mission metadata PATCH makes an artifact Cloud-runnable.
- Automatically changing Mission Studio's selected Local/Cloud runtime.
- Executing a mission without explicit user authorization and the applicable Local preflight gates.
- Adding new primitives to the autonomy SDK or changing a separate autonomy repository in this implementation. If a requested capability does not exist, report the gap and propose a separate SDK change workflow for approval.
- Reworking unrelated report/evidence or release behavior.

## Architecture and Semantics

### Mission targeting

Mission reads may show an explicitly selected mission, but writes and execution require explicit `project_id` and `mission_id`. Creation requires an explicit authorized `project_id`; no hard-coded project fallback is allowed. If the target is absent, ambiguous, unavailable, or not writable, return a clear error before modifying any file or dispatching a run.

### Separate mission representations

- **Plan mode:** preserves the full `plan.json` structure, including sequences, all action records, IDs, and additional metadata.
- **Code mode:** preserves `script.py` exactly and persists `mission.json` with `codeMode=true`.
- **Cloud metadata sync:** is a separate operation. It must not silently convert Code mode to Plan mode or claim that `script.py` was uploaded. Until the Cloud API supports and verifies the same artifact, Code-mode Cloud sync must fail clearly or be reported as metadata-only/unsupported per the exact operation semantics.

Any patch mechanism that cannot round-trip an existing Plan shape losslessly must reject that shape without writing, rather than reconstructing it from a reduced parser model.

### Validation status

Validation output distinguishes these stages:

1. **Syntax-valid:** the Python file parses.
2. **Static-review pass/warnings/fail:** AST and semantic checks find no prohibited or unsupported usage at the implemented analysis depth.
3. **Mode-valid:** mission metadata and authored representation agree (Plan versus Code); Code-only missions need not contain visual waypoints.
4. **SDK-compatible:** referenced imports/calls match documented/current supported SDK interfaces where locally verifiable.
5. **Runtime-ready:** only reported when required runtime, vehicle, world, and preflight information is available and passes; static checks alone never establish this.
6. **Executed/evidence-verified:** only reported after a correlated run completes and available native evidence meets requirements.

The terms must not be collapsed into a single `valid: true` that implies execution readiness. Unknown runtime compatibility remains `UNKNOWN`.

### Independent review

The Claude Code project skill asks a separate read-only subagent to review the exact read-back Plan or Code artifact against the mission requirements and validation results. The reviewer returns findings and a verdict; it must not edit the mission or dispatch it. The MCP supplies the exact mission data, SDK references, validation tools, and prompts. It does not itself provide an LLM or guarantee that an arbitrary MCP host has subagent support; when a separate reviewer cannot be launched, report review as unavailable and do not claim independently reviewed.

A reviewed artifact is `ready_for_user_to_execute` only when explicit target identity, successful save/read-back, mode-consistent validation, reviewer outcome, and applicable world/vehicle constraints are all clear. Cloud execution readiness is a separate state and remains unavailable without an app-supported runtime path.

### Execution and observation

Existing direct GCS/Docker execution, telemetry, and logs are explicitly **Local Docker-only**. A local run requires explicit authorization for that run, explicit target identity, no conflicting active script/run, a fresh safety preflight, and a clear confirmation that the requested backend is Local. These calls must never be used when the app-selected backend is Cloud or unknown. The Claude workflow defaults to user-run handoff; it can offer Local execution as a distinct follow-up.

Local observation and report outputs must retain run/mission correlation where available. A dispatch acceptance or current telemetry snapshot is not a terminal completion or evidence-backed success. If the current local interface cannot provide an execution ID or artifact provenance, label it unverified.

For a Cloud-selected Mission Studio run, the MCP may help author and inspect locally accessible mission files, but may not dispatch through guessed/private Cloud routes. Until an external app bridge exists, the user runs the mission in SkyTrack. Cloud logs, telemetry, and reports are only usable when their mission/run identity can be verified; otherwise mark them unavailable/unverified.

## Workflow

1. **Understand requirements:** turn the assignment into explicit goals, constraints, authoring needs, and acceptance criteria.
2. **Resolve exact target:** obtain explicit project and mission IDs, or ask before creating in a specified project. Read current mission state without mutation. Stop on ambiguity or access failure.
3. **Choose representation:** select Plan or Code based on requirements and documented SDK support, independently from simulation runtime.
4. **Inspect before editing:** preserve complete raw Plan data; inspect the script and metadata in Code mode. Determine whether the requested action shape can be supported without lossy conversion.
5. **Author minimally:** use the Level 1–6 template/reference that fits, or edit the existing Plan/Code artifact without changing unrelated fields.
6. **Save and read back:** require successful file/metadata writes and exact identity/mode/content comparison after re-read. Failed or partial writes are not success.
7. **Validate by stage:** run Plan- or Code-aware validation. Report syntax, static checks, SDK compatibility, runtime readiness, and unknowns separately.
8. **Independent review:** obtain read-only review from a separate subagent where available; incorporate findings by editing only after reviewer completion, then save/read-back/revalidate/re-review as appropriate.
9. **Ready-to-run handoff:** provide explicit mission/project IDs, representation, files changed, validation and review results, runtime limitations, and the user's next SkyTrack action.
10. **Optional Local run:** only on explicit user request, after Local backend confirmation and safety preflight. Observe to terminal state and collect only correlated local evidence. Stop on backend mismatch or any failed/unknown safety gate.
11. **Cloud run:** remains a user-operated Mission Studio action until a supported bridge is implemented. Never claim it ran from MCP metadata sync.
12. **SDK gap:** if needed APIs are not in the verified SDK reference/templates, do not fabricate them or modify the SDK repository in this flow. Report the unsupported capability and offer a separately approved SDK-development proposal.

## Safety and Permissions

- Existing unrelated missions are never overwritten; all writes name their explicit project and mission.
- Create mission only in an explicit project selected/authorized by the user. Respect view-only and owner restrictions; surface permission errors.
- Before any write, capture or retain enough original state for rollback; reject lossy edits without mutation.
- Do not change Mission Studio's Local/Cloud selection from MCP.
- Do not start, stop, or replace a Local Docker run as an implicit recovery action; surface conflicts first.
- No Cloud fallback, no Cloud dispatch through undocumented/private interfaces, and no Local execution when backend is Cloud or unknown.
- No test mission cleanup/deletion without separate authorization.
- Native report and provenance requirements remain in force; missing identity or evidence stays `UNKNOWN`.

## Test Strategy

### Offline regression tests

- Explicit target IDs are required for mutation; ambiguous/missing mission and missing project never select or invent a target.
- Read-only/missing mission and permission failures happen before writes.
- Plan round-trip fixtures with multiple sequences, standalone actions, multiple attached actions, IDs, and unknown metadata remain byte/structure equivalent when unchanged.
- Unsupported Plan patches fail before disk mutation; valid targeted edits preserve unrelated data.
- Python script write failure and mission metadata write failure return failure; `codeMode` read-back must match.
- Code-only mission is mode-valid without visual waypoints; empty/invalid/missing entry point or unsupported SDK calls cannot be reported as execution-ready.
- Each Level 1–6 template parses and passes the appropriate current static checks; tests do not treat parse success alone as runtime proof.
- Clone/import preserve both Plan and Code data, or refuse unsupported source shapes without silent loss.
- Cloud sync cannot force Code mode false or imply script upload when the API does not persist the script.
- `/skytrack` defaults to handoff; direct execution is invoked only after explicit Local selection/authorization and all preflight gates.
- Cloud/unknown backend never reaches direct local Docker/GCS functions.
- Ready-to-run status requires exact read-back, mode-consistent validation, and an independent-review result when Claude Code subagents are available.

### Optional live tests

Live runs are separate, explicitly authorized actions. Use a disposable mission and preserve all existing missions/resources. Do not use live Cloud dispatch until a supported bridge is available. Local integration may be tested only if Docker/GCS/telemetry are healthy, runtime is explicitly Local, and the mission passes all preflight checks. A simulation acceptance response alone is not success; collect a terminal state and correlated evidence. If these gates cannot be verified, stop at the handoff and report what remains untested.

## Implementation Boundary

This phase is implementable in the SkyTrack MCP checkout: mission targeting, safe storage round-trips, mode-aware validation, SDK-reference/template use, reviewer-guided `/skytrack` workflow, honest Local-only execution labels, and tests. It does not need private Mission Studio IPC to provide the primary authoring/review/handoff outcome.

A future app bridge is a separate prerequisite for MCP-triggered Cloud dispatch and Cloud run observation. It must be Mission Studio-owned, externally callable, versioned, and provide selected runtime, permissions, artifact operations, dispatch identity, logs, telemetry, and reports. The exact protocol is not specified or guessed by this design.
