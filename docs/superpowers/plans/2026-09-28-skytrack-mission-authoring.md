# SkyTrack Mission Authoring and Ready-to-Run Handoff Implementation Plan

> **Status:** Superseded on 2026-09-28 by the unapproved design draft [`2026-09-28-skytrack-agent-workflow-design.md`](../specs/2026-09-28-skytrack-agent-workflow-design.md). Retained for historical reference; do not execute this plan. A new plan requires written-spec approval.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Each task gets an implementation agent and an independent review gate before the next task. Keep user-requested execution method: sub-agent-driven.

**Goal:** Make Claude Code reliably target, author, save, validate, independently review, and hand off SkyTrack Plan and Code missions without silently changing mission identity, losing plan data, overstating validation, or routing a Cloud request into local Docker/GCS.

**Architecture:** Keep the existing Python MCP and ClientData mission model. Add explicit targets and verified transactional writes, preserve raw Plan/mission JSON through patching, return mode-specific validation/readiness, mark Cloud sync limitations, gate direct execution as explicitly Local Docker-only, and revise `/skytrack` guidance to stop at a reviewed user handoff by default.

**Tech Stack:** Python 3.10+, MCP FastMCP, Pydantic v2, pytest/pytest-asyncio, ruff, Markdown Claude Code project skills.

**Spec:** `docs/superpowers/specs/2026-09-28-skytrack-app-bridge-design.md`

## Global Constraints

- Mission mutations require explicit `project_id` and `mission_id`; do not infer the most-recent mission or invent a project ID.
- Preserve visual Plan data losslessly or reject an edit whose data shape cannot be safely preserved.
- Code mode persists `script.py` separately with `codeMode=true`; never flatten it into a visual Plan.
- Syntax/static validation, SDK compatibility, runtime readiness, and executed/evidence-verified are distinct states.
- Local direct execution is opt-in and Local Docker-only; Cloud or unknown backend must never call local GCS/Docker functions.
- Do not implement or guess private Electron IPC, Cloud proxy routes, or an app bridge.
- Do not modify unrelated report/evidence or release-gating behavior.
- Do not commit, push, merge, or delete test missions unless the user separately asks.

## Review Focus

1. Missing/ambiguous project or mission IDs and duplicate mission IDs across projects must fail before a write; Task 1 tests this.
2. Partial filesystem failures and metadata-write failures must restore prior mission artifacts and must not report success; Task 1 tests this.
3. Multiple sequences, standalone actions, multiple adjacent actions, IDs, and unknown Plan metadata must not be lost by patching; Task 2 tests preservation and refusal-before-write.
4. A parseable Code script with no runnable SkyTrack entry point must not be labeled execution-ready; an SDK symbol absent from the checked reference remains compatibility-unknown and also blocks execution readiness; Task 3 tests both states.
5. Cloud or unknown backend, missing Local execution confirmation, active local script, mismatched Local world/vehicle, or missing preflight telemetry must stop before GCS/Docker access; Task 5 tests no-call behavior.

---

## File Structure

- `src/skytrack_mcp/clients/storage_sync.py` — exact target resolution and transactional Plan/mission/script writes.
- `src/skytrack_mcp/mission/models.py` — retain non-wire raw Plan and metadata source documents during a patch operation.
- `src/skytrack_mcp/mission/parser.py` — parse canonical convenience fields while retaining raw source JSON for lossless serialization.
- `src/skytrack_mcp/mission/patcher.py` — patch supported Plan shapes without reducing/reconstructing unrelated source data; validate before commit and preserve rollback snapshots.
- `src/skytrack_mcp/mission/validator.py` and `src/skytrack_mcp/autonomy_sdk.py` — mode-aware validity and Code readiness distinct from AST validity.
- `src/skytrack_mcp/clients/cloud_client.py`, `src/skytrack_mcp/server.py`, `src/skytrack_mcp/mcp/tools.py` — propagate explicit IDs, prevent Code-mode Cloud downgrade/false script-upload claims, and gate Local-only execution.
- `src/skytrack_mcp/simulation/preflight.py` — pure Local Docker mission preflight shared by Plan and Code execution; no app/Cloud routing logic.
- `src/skytrack_mcp/mcp/prompts.py`, `src/skytrack_mcp/mcp/resources.py`, `.claude/skills/skytrack/SKILL.md`, and selected `skills/skytrack-*/SKILL.md` — author/review/handoff default and honest backend boundaries.
- `tests/test_storage_sync.py`, `tests/test_mission_roundtrip.py`, `tests/test_code_readiness.py`, `tests/test_local_execution_gate.py` — focused regression coverage.
- `tests/test_server.py`, `tests/test_mcp_protocol.py`, `tests/test_skill_entrypoint.py` — update existing behavior and end-to-end MCP/skill contracts.

## Interfaces Produced by the Plan

Task 1 establishes these storage contracts:

```python
def resolve_mission_dir(
    mission_id: str | None = None,
    client_data_dir: Path | None = None,
    project_id: str | None = None,
    create_if_missing: bool = False,
    *,
    require_explicit_target: bool = False,
) -> tuple[Path, str, str]: ...


def commit_mission_files(mission_dir: Path, updates: dict[str, str]) -> None: ...
```

`require_explicit_target=True` requires both IDs and resolves their exact pair. `commit_mission_files` accepts only `mission.json`, `plan.json`, and `script.py`. Read-only context listing may continue showing the most-recent local mission; no mutation path may use that behavior.

Task 2 adds these internal-only model fields:

```python
raw_plan: dict[str, Any] = Field(default_factory=dict, exclude=True)
raw_mission: dict[str, Any] = Field(default_factory=dict, exclude=True)
```

The parser fills them from the source documents. The patcher uses them as the source of truth and refuses unsupported structural edits before writing.

Task 3 adds `syntax_valid`, `static_valid`, `sdk_compatibility`, `execution_ready`, and `readiness_issues` to Code validation results while retaining `valid` for existing clients as the syntax/static error summary. An SDK symbol absent from the local reference yields `sdk_compatibility="UNKNOWN"` and `execution_ready=False`, not an invented API error. `tool_skytrack_validate_mission` returns mode-consistent Plan or Code validation plus an explicit readiness state; `valid` alone never means runtime-ready.

Task 5 adds required `backend: Literal["local_docker", "cloud"]`, `project_id`, and `mission_id` arguments to direct-run and observation tools. `cloud` returns `CAPABILITY_UNAVAILABLE` before calling GCS or Docker; Local Docker runs are direct MCP operations independent of the app's runtime selector and require the caller to explicitly confirm Local Docker. Local preflight returns `{ready: bool, blockers: list[str]}`.

---

### Task 1: Explicit Mission Targets and Transactional Saves

**Files:**
- Modify: `src/skytrack_mcp/clients/storage_sync.py`
- Modify: `src/skytrack_mcp/server.py`
- Modify: `src/skytrack_mcp/mcp/tools.py`
- Create: `tests/test_storage_sync.py`
- Update: `tests/test_server.py`

**Interfaces:**
- Consumes: current `list_all_missions`, `write_visual_route`, `write_python_script`, and `resolve_mission_dir` APIs.
- Produces: `resolve_mission_dir(..., require_explicit_target=True)` and `commit_mission_files(mission_dir, updates)` as defined above. All mission file writes pass explicit `project_id` and `mission_id`.

- [ ] **Step 1: Write failing target-resolution tests**

```python
def test_write_resolution_requires_project_and_mission(tmp_path):
    from skytrack_mcp.clients.storage_sync import resolve_mission_dir
    from skytrack_mcp.core.errors import SkyTrackError

    with pytest.raises(SkyTrackError):
        resolve_mission_dir(
            client_data_dir=tmp_path,
            require_explicit_target=True,
        )
```

Add companion tests for a valid exact pair, a mission ID found under a different project, and a missing project on `create_if_missing=True`; assert the resolver never creates the legacy hard-coded project.

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `pytest tests/test_storage_sync.py -q`  
Expected: FAIL because `require_explicit_target` is not implemented and current resolution defaults to most-recent/hard-coded project.

- [ ] **Step 3: Implement exact write-target resolution**

Add `require_explicit_target` to `resolve_mission_dir`. For writes, require both IDs, strip only the existing `prj-`/`mis-` prefixes, and match the pair exactly. Preserve most-recent behavior only for read-only calls that deliberately omit IDs. Remove the hard-coded project fallback from the create path. Raise `SkyTrackError(MISSION_INVALID, ..., suggested_action=...)` for missing explicit IDs and `MISSION_NOT_FOUND` for an unknown exact pair.

- [ ] **Step 4: Run target-resolution tests**

Run: `pytest tests/test_storage_sync.py -q`  
Expected: PASS for exact pair, missing IDs, cross-project mismatch, and create without explicit project.

- [ ] **Step 5: Add failing transactional write/read-back tests**

Test `commit_mission_files` with two existing files and one injected write failure; after the exception, assert both original file contents remain. Test successful JSON/script writes and assert exact read-back. Test that `write_python_script` fails rather than swallowing an invalid/missing `mission.json` update.

- [ ] **Step 6: Implement `commit_mission_files` and strict script save**

Capture original bytes before writing. Stage updates in temporary siblings, replace destination files, read each destination back, and compare it with the intended contents. On any exception or mismatch, restore original bytes or remove files that did not previously exist, then raise `MISSION_WRITE_FAILED`. Use this helper for `write_visual_route` and `write_python_script`; do not catch metadata write errors and return success.

- [ ] **Step 7: Propagate explicit IDs through write tools**

Add required `project_id` and `mission_id` to `draw_route_on_map`, saved `plan_coverage_route`, `write_and_save_uav_script`, and the `tool_skytrack_set_mission` wrapper. Require the same pair for `tool_skytrack_patch_mission`, `tool_skytrack_save_mission`, `tool_skytrack_select_world`, `tool_skytrack_select_vehicle`, report export/harvest operations that write files, and every caller that persists a conversion or route. When `plan_coverage_route(save_to_mission_ui=False)` or conversion runs without saving, leave IDs optional. Update all internal calls to pass the exact pair returned by a prior explicit project/mission read or create. Writers must fail on malformed existing JSON instead of treating it as empty data. Add tests proving omitted IDs and malformed files fail before snapshot creation or file mutation.

- [ ] **Step 8: Run storage and server tests**

Run: `pytest tests/test_storage_sync.py tests/test_server.py -q`  
Expected: PASS; omitted target IDs fail before filesystem changes; explicitly targeted writes persist and read back.

---

### Task 2: Lossless Plan Parsing and Safe Patch Semantics

**Files:**
- Modify: `src/skytrack_mcp/mission/models.py`
- Modify: `src/skytrack_mcp/mission/parser.py`
- Modify: `src/skytrack_mcp/mission/patcher.py`
- Create: `tests/test_mission_roundtrip.py`
- Update: `tests/test_server.py`

**Interfaces:**
- Consumes: explicit mission path and Task 1 transactional write helper.
- Produces: canonical reads that retain raw source `plan.json`/`mission.json`; supported metadata and waypoint patches preserve unrelated raw fields; unsupported structural edits fail before snapshot or write.

- [ ] **Step 1: Add failing lossless-plan tests**

Create a fixture with two sequences, sequence metadata, a navigate action, two adjacent standalone payload/camera actions, an action ID, and unknown action metadata. Assert `parse_ui_mission(...).raw_plan` and `.raw_mission` equal the source dictionaries, and `canonical_to_ui_dicts(parsed)` returns the exact source dictionaries when no canonical field changed. Add a metadata-only patch test that updates `world` while `plan.json` remains unchanged. Add a test that unsupported waypoint patches reject before mutation; keep `write_visual_route` as the explicit full-route authoring operation and never invoke it implicitly from a metadata/waypoint patch.

- [ ] **Step 2: Add failing unsupported-shape rollback test**

Call `MissionPatcher.patch_mission({"set_waypoints": [...]})` on a multi-sequence plan shape the patcher cannot safely map. Assert a structured error, no new snapshot, and byte-identical `mission.json`/`plan.json`.

- [ ] **Step 3: Run the focused tests and confirm they fail**

Run: `pytest tests/test_mission_roundtrip.py -q`  
Expected: FAIL because the canonical model discards raw document structure and serializes a reduced single-route model.

- [ ] **Step 4: Retain raw source documents in `CanonicalMission`**

Add excluded `raw_plan` and `raw_mission` fields with empty-dict factories. In `parse_ui_mission`, deep-copy the exact input dictionaries into those fields while keeping `waypoints`/`raw_actions` as convenience views. Do not use `raw_actions` as a replacement for the original sequences.

- [ ] **Step 5: Patch raw documents and validate before write**

In `MissionPatcher.patch_mission`, apply metadata-only changes to a copy of `raw_mission` and leave `raw_plan` untouched. For waypoint operations, update only a verified supported one-route shape while retaining root/sequence metadata and stable IDs; if actions/sequences cannot be mapped without dropping information, raise `MISSION_INVALID` with an unsupported-shape explanation. Keep full visual route replacement in the explicit `write_visual_route` operation, not in patching. Build and validate the patch candidate before creating a snapshot. Snapshot and write only after validation succeeds, using Task 1's transactional helper. Update `canonical_to_ui_dicts` to return deep copies of raw source documents for an unchanged canonical mission, and to preserve raw top-level metadata when supported canonical fields are updated.

- [ ] **Step 6: Run parser/patcher regression tests**

Run: `pytest tests/test_mission_roundtrip.py tests/test_server.py -q`  
Expected: PASS; unknown fields and extra sequences survive metadata edits, and unsupported waypoint edits leave files and snapshots unchanged.

---

### Task 3: Code-Mode Validation and Honest Readiness

**Files:**
- Modify: `src/skytrack_mcp/autonomy_sdk.py`
- Modify: `src/skytrack_mcp/mission/validator.py`
- Modify: `src/skytrack_mcp/mcp/tools.py`
- Modify: `src/skytrack_mcp/server.py`
- Create: `tests/test_code_readiness.py`
- Update: `tests/test_autonomy_levels.py`
- Update: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 exact mission read-back and Task 2 canonical raw script/metadata.
- Produces: `validate_uav_python_code(code)` includes `syntax_valid`, `static_valid`, `sdk_compatibility` (`"REFERENCE_MATCH"` or `"UNKNOWN"`), `execution_ready`, and `readiness_issues`; `tool_skytrack_validate_mission(project_id, mission_id)` returns separate mode validity and readiness fields.

- [ ] **Step 1: Write failing Code-only and incomplete-entry tests**

```python
def test_code_only_mission_is_not_rejected_for_missing_visual_waypoints():
    mission = CanonicalMission(
        project_id="P1", mission_id="M1", code_mode=True,
        python_script=get_uav_python_sdk_reference_data()["example_script"],
    )
    assert validate_canonical_mission(mission).valid is True


def test_parseable_script_without_skytrack_entrypoint_is_not_execution_ready():
    result = validate_uav_python_code("def scenario(ctx):\n    return None\n")
    assert result["syntax_valid"] is True
    assert result["execution_ready"] is False
```

Add tests for `code_mode=True` with no script, missing `boot_drone`/`scenario`/`main` runner shape, unknown imported `local_planner` symbol, and the six official templates.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `pytest tests/test_code_readiness.py tests/test_autonomy_levels.py -q`  
Expected: FAIL because Code-only validation currently demands waypoints and parseable incomplete code can have `valid=True`.

- [ ] **Step 3: Add separate validation dimensions**

Keep the existing `valid` field as the no-static-errors summary for compatibility. Add `syntax_valid`, `static_valid`, `execution_ready`, and `readiness_issues`. Mark readiness false when required SkyTrack entry-point/runner structure is missing or an imported SDK symbol is not present in the checked reference. Do not claim that AST checks prove ROS runtime success.

- [ ] **Step 4: Make mission validation mode-aware**

For `code_mode=True`, require a non-empty script and run the Code validator; do not require visual waypoints. For Plan mode, retain the current route/action rules. Return separate fields such as `mode_valid`, `validation`, `execution_ready`, and `readiness_issues`; do not collapse them into one `valid` result.

- [ ] **Step 5: Run Code and existing template tests**

Run: `pytest tests/test_code_readiness.py tests/test_autonomy_levels.py tests/test_server.py -q`  
Expected: PASS; Levels 1–6 remain syntax/static-valid, Code-only mode is accepted only with script content, and incomplete scripts are never described as execution-ready.

---

### Task 4: Honest Cloud Sync and Clone/Import Fidelity

**Files:**
- Modify: `src/skytrack_mcp/server.py`
- Modify: `src/skytrack_mcp/mcp/tools.py`
- Create: `tests/test_cloud_mission_sync.py`
- Update: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 explicit target resolution and Task 2 full raw Plan/Code state.
- Produces: Cloud sync requires explicit IDs; Code mode returns a structured metadata-only/unsupported result before PATCH because the current API does not upload `script.py`; clone/import reject representations they cannot preserve instead of flattening them.

- [ ] **Step 1: Add failing Cloud Code-mode sync test**

Mock `update_cloud_mission`, load a Code-mode mission from a temporary ClientData directory, and call `sync_mission_to_cloud(project_id="P1", mission_id="M1")`. Assert the result is explicitly unsupported/metadata-only, the mission remains `codeMode=True`, and `update_cloud_mission` was not called.

- [ ] **Step 2: Add failing clone/import fidelity tests**

For a Code-mode source with `script.py` and a Plan with more sequences than the Cloud create payload supports, assert clone/import fail before `create_cloud_mission` is called. Add a simple supported visual fixture and assert its action order is preserved.

- [ ] **Step 3: Run focused Cloud tests**

Run: `pytest tests/test_cloud_mission_sync.py -q`  
Expected: FAIL because Cloud command construction hard-codes `codeMode=False`, omits script content, and clone/import select only the first sequence.

- [ ] **Step 4: Implement explicit Cloud capability results**

Require `project_id` and `mission_id` on Cloud sync, and require an explicit destination `target_project_id` on clone. Detect `codeMode=True` before building or sending the PATCH; return a structured `CAPABILITY_UNAVAILABLE` result that says the Cloud API does not persist the script. Do not rewrite local mode metadata. For sync/clone/import, preserve only the exact one-sequence visual shapes proven representable by the current Cloud payload; reject Code, multiple-sequence, standalone/unknown action, or unknown metadata shapes before creating or PATCHing a Cloud record.

- [ ] **Step 5: Run Cloud and MCP handler tests**

Run: `pytest tests/test_cloud_mission_sync.py tests/test_server.py -q`  
Expected: PASS; no Code-mode sync calls reach Cloud and no clone/import silently truncates Plan or script data.

---

### Task 5: Explicit Local-Only Execution Gate and Preflight

**Files:**
- Create: `src/skytrack_mcp/simulation/preflight.py`
- Modify: `src/skytrack_mcp/server.py`
- Modify: `src/skytrack_mcp/mcp/tools.py`
- Modify: `src/skytrack_mcp/clients/docker_exec.py`
- Create: `tests/test_local_execution_gate.py`
- Update: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 exact mission/project identity and Task 3 `execution_ready` status.
- Produces: direct-run, telemetry, and log tools require `backend: Literal["local_docker", "cloud"]`; `project_id` and `mission_id` are required for mission-specific operations. Cloud returns unsupported before GCS/Docker access. The Local option is explicitly a direct MCP-to-Local-Docker path, independent of Mission Studio's selected environment, and may be called only after user confirmation. A pure `check_local_execution_preflight(mission, runtime, telemetry, script_running) -> dict[str, Any]` reports `{ready, blockers}`.

- [ ] **Step 1: Write failing no-dispatch and preflight tests**

Mock route GCS dispatch, Python container execution, Local Docker lifecycle, telemetry, and log readers. Assert `backend="cloud"`, missing Local confirmation, missing target IDs, mismatched runtime world/vehicle, disconnected telemetry, armed/not-landed state, unknown/low battery, and an already-running script all block before any Local GCS/Docker call. Assert Cloud/unknown observations do not call local telemetry/log functions.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `pytest tests/test_local_execution_gate.py tests/test_server.py -q`  
Expected: FAIL because execution tools have no backend argument, only check telemetry connectivity in the closed-loop helper, and the Python container runner stops an existing script.

- [ ] **Step 3: Implement pure Local preflight**

Create `check_local_execution_preflight(mission, runtime, telemetry, script_running)`. Require Local backend selection, matching mission/runtime world and vehicle, connected telemetry, `landed_state == "ON_GROUND"`, `is_armed is False`, battery percentage strictly above 15, and no running user script. Missing values become blockers, not defaults. Return blocker names/messages without side effects.

- [ ] **Step 4: Gate direct execution tools**

Add required `backend: Literal["local_docker", "cloud"]` to direct Plan/Code execution, closed-loop, control, telemetry, observation, and log tools; add explicit `project_id`/`mission_id` to mission-specific operations. Cloud returns `CAPABILITY_UNAVAILABLE` before any local telemetry/GCS/Docker call. For `local_docker`, require a clear user request for direct Local execution, load the exact mission, check Code `execution_ready` where applicable, call Local preflight, and return `SIMULATOR_NOT_READY` without dispatch when blocked. Tool descriptions must state that Local Docker is a direct MCP path independent of Mission Studio's runtime selector; no workflow may imply that this setting was read or changed.

- [ ] **Step 5: Prevent automatic replacement and preserve run identity**

Change `run_uav_python_in_container` to refuse an existing running user script by default; do not stop/replace it implicitly. Keep explicit stop as a separate requested action. In `run_mission_and_wait_completion`, return the dispatch `execution_id` and backend with the observation; name observed terminal status honestly and do not claim report verification from touchdown alone.

- [ ] **Step 6: Run execution gate tests**

Run: `pytest tests/test_local_execution_gate.py tests/test_server.py -q`  
Expected: PASS; all blocker cases leave dispatch/container mocks untouched; a valid, explicitly Local test reaches the mocked lower-level call and preserves the returned execution ID.

---

### Task 6: Claude Author–Review–Handoff Workflow and MCP Guidance

**Files:**
- Modify: `.claude/skills/skytrack/SKILL.md`
- Modify: `skills/skytrack-operator/SKILL.md`
- Modify: `skills/skytrack-mission-authoring/SKILL.md`
- Modify: `skills/skytrack-simulation/SKILL.md`
- Modify: `skills/skytrack-report-analysis/SKILL.md`
- Modify: `skills/skytrack-mission-verification/SKILL.md`
- Modify: `src/skytrack_mcp/mcp/prompts.py`
- Modify: `src/skytrack_mcp/mcp/resources.py`
- Modify: `README.md`
- Update: `tests/test_skill_entrypoint.py`
- Update: `tests/test_mcp_protocol.py`

**Interfaces:**
- Consumes: explicit target parameters, mode-aware validation, Cloud unsupported results, and Local-only execution gate from Tasks 1–5.
- Produces: `/skytrack` defaults to author/save/read-back/validate/independent review/handoff. It invokes a read-only Claude Code subagent reviewer when available and reports review unavailable otherwise. Execution is a separate explicit Local-only follow-up; Cloud execution is a user-run Mission Studio step until a supported bridge exists.

- [ ] **Step 1: Add failing guidance/protocol assertions**

Add tests that the solve-mission MCP prompt includes explicit mission selection, read-back, reviewer handoff, and does not instruct automatic simulation start. Add skill assertions that Plan and Code are separate, most-recent mission is read-only context only, Cloud does not fall back to local, and the reviewer cannot edit or dispatch.

- [ ] **Step 2: Run the prompt/skill tests and confirm they fail**

Run: `pytest tests/test_skill_entrypoint.py tests/test_mcp_protocol.py -q`  
Expected: FAIL because the current prompt says to launch and rerun automatically and the project skill has no independent-review handoff.

- [ ] **Step 3: Update the project dispatcher and authoring playbook**

Document the author/save/read-back/mode-aware-validate/review/handoff sequence. Require explicit target IDs before writes. Tell the separate reviewer agent to inspect the exact saved artifact, requirement checklist, SDK reference, and validation result read-only; do not ask it to mutate files or execute. If no subagent tool is available, return `review_unavailable` rather than claiming reviewed.

- [ ] **Step 4: Update execution, report, and verification playbooks**

Label direct GCS/Docker tools Local Docker-only. Keep dispatch opt-in, require the Local preflight from Task 5, and explain that Cloud runs remain in Mission Studio. After a user-run, inspect only mission/run-correlated reports/logs/telemetry; missing Cloud artifacts stay unavailable/unverified.

- [ ] **Step 5: Update MCP prompt, operator resource, and README**

Change `skytrack-solve-mission` to stop at a reviewed handoff by default; make run authorization a separate step. Update the operator resource and README capability list so Cloud project/mission metadata APIs are not described as Cloud simulation dispatch or telemetry.

- [ ] **Step 6: Run skill and MCP protocol tests**

Run: `pytest tests/test_skill_entrypoint.py tests/test_mcp_protocol.py -q`  
Expected: PASS; the slash skill remains discoverable, MCP prompt/resource language matches the handoff behavior, and tool schemas expose Local-only execution requirements.

---

### Task 7: Full Offline Validation and Independent Review

**Files:**
- Review: all files changed in Tasks 1–6
- Test: all offline test suites

**Interfaces:**
- Consumes: completed Tasks 1–6.
- Produces: a clean offline verification report plus independent reviewer findings; no live dispatch, Cloud API mutation, or test mission creation in this phase.

- [ ] **Step 1: Run focused regression suites**

Run: `pytest tests/test_storage_sync.py tests/test_mission_roundtrip.py tests/test_code_readiness.py tests/test_cloud_mission_sync.py tests/test_local_execution_gate.py tests/test_autonomy_levels.py tests/test_skill_entrypoint.py tests/test_server.py tests/test_mcp_protocol.py -v`  
Expected: PASS.

- [ ] **Step 2: Run the complete offline suite and lint**

Run: `pytest -m "not live_simulation" -v`  
Expected: PASS; report any pre-existing unrelated failure separately. Then run `ruff check src tests` and fix only findings introduced by this work.

- [ ] **Step 3: Request final read-only review**

Ask the designated reviewer Claude session to review the diff for mission targeting, data loss, readiness overclaims, accidental Cloud-to-Local calls, and unrequested release/evidence changes. Resolve valid findings in-scope, rerun the affected tests, and report any deferred finding.

- [ ] **Step 4: Verify worktree scope**

Run `git status --short` and `git diff --check`. Expected: only the spec, implementation plan, and implementation/test/docs files described above are changed; no simulation was started and no mission or Cloud record was created.

## Execution Notes

- The user selected sub-agent-driven implementation. After approving this plan, invoke `superpowers:subagent-driven-development`; do not implement inline before that approval.
- Review and test each task before starting the next task. Keep external Mission Studio bridge work and upstream autonomy SDK changes out of this branch unless the user separately approves them and provides a supported source/contract.
- Do not run `live_simulation` tests or change the current Mission Studio runtime as part of offline validation.
