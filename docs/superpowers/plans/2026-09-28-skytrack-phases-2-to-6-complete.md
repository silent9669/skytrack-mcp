# SkyTrack MCP Phases 2–6 Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phases 2 through 6 of the approved SkyTrack Agent Workflow Specification: lossless transactional mission authoring (Plan and Code modes), user-triggered post-run report/media debugging without live telemetry pollution, pinned Autonomy SDK & organizer perception model post-processing (`det-h2026-v26n-b-fp32-640`), the 2026 Semifinal An Giang rule pack, and the global user-scope Claude Code plugin.

**Architecture:**
1. **Phase 2 (Lossless Mission Authoring & Permission Gates):** Atomic pre-write snapshots, lossless raw `plan.json` preservation, independent Plan (`plan.json`) and Code (`script.py`) representations with `codeMode` read-back hash verification, and strict `verify_project_edit_permission` gating (`PERMISSION_UNVERIFIED` / `DENIED` fail-safe).
2. **Phase 3 (Explicit Post-Run Report & Debug Workflow):** Run-scoped native `skytrack-mission-report*.json` parser completely free of live `fetch_live_mavlink_telemetry()` or fabricated battery fallbacks; exact `(project_id, mission_id, execution_id)` correlation; user-provided media/log ingestion (`USER_PROVIDED`); same-mission repair and user-rerun handoff.
3. **Phase 4 (Pinned Autonomy SDK, Organizer Model & Semifinal Rule Pack):** Pinned `GetSkyTrack/skytrack-autonomy-example@bb0f5ba611c59cd68d32d1fe04b40765836a1b33` reference; AST validator checking `skytrack_autonomy` (`Detector`, `Sprayer`) and `local_planner` (`CameraSense`, `VideoRecorder`, `Snapshot`, `boot_drone`) provenance and frame-sequence correlation; nadir camera pixel-to-ENU projection and spray cone dosage geometry; 2026 Semifinal An Giang rule pack (<=40m AGL flight, <=20m AGL spray, 5m residential buffer with CS1-CS4 charging pad approach exception, <=3m touchdown, 15m/90m timing, Mission Break + manual resume).
4. **Phase 5 (Global Claude Code Plugin & Multi-Host Setup):** `.claude-plugin/plugin.json`, plugin-relative `.mcp.json` and `bin/skytrack-mcp-launcher.sh`, natural-language `skills/skytrack/SKILL.md` with optional `/skytrack` entrypoint, and OpenCode/Codex stdio setup instructions.

**Tech Stack:** Python 3.10+, FastMCP, Pydantic v2, AST, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-skytrack-agent-workflow-design.md`

## Global Constraints

- Default MCP server and plugin must NEVER register live simulation dispatch, flight control, container lifecycle, or unrestricted UI clicking tools.
- Never write to a mission when `edit_authorization` is `DENIED` or `UNVERIFIED`, or when the mission is an immutable judge snapshot.
- Never overwrite or flatten `plan.json` when saving `script.py`, and never delete `script.py` when editing `plan.json`.
- Never call `fetch_live_mavlink_telemetry()` or substitute 100% battery inside post-run report parsing.
- Never train, fine-tune, or replace the organizer perception model (`det-h2026-v26n-b-fp32-640`), and never relabel its `stressed` class as a specific disease without evidence.
- Strictly zero Variant B private ground-truth data or evaluator internals.

---

### Task 1 (Phase 2): Lossless Plan & Code Transaction Manager with Read-Back Verification

**Files:**
- Create: `src/skytrack_mcp/mission/transaction.py`
- Modify: `src/skytrack_mcp/mission/patcher.py`
- Modify: `src/skytrack_mcp/clients/storage_sync.py`
- Test: `tests/test_mission_transaction.py`

**Steps:**
- [ ] Write failing tests in `tests/test_mission_transaction.py` for:
  - Pre-write snapshot creation and rollback on write/read-back mismatch.
  - Lossless preservation of multi-sequence `plan.json` with standalone actions, attached actions, IDs, and unknown keys.
  - Independent Code save (`script.py` + `codeMode=True`) preserving existing `plan.json` byte-for-byte.
  - Independent Plan save (`plan.json` + `codeMode=False`) preserving existing `script.py` byte-for-byte.
  - Blocking writes when `edit_authorization != VERIFIED` (`PERMISSION_UNVERIFIED` or `DENIED`).
- [ ] Implement `src/skytrack_mcp/mission/transaction.py` and wire gated authoring tools (`tool_skytrack_author_plan`, `tool_skytrack_author_code`).
- [ ] Verify all tests in `tests/test_mission_transaction.py` pass.

---

### Task 2 (Phase 3): Run-Scoped Post-Run Report Parser & Explicit Debug Workflow

**Files:**
- Modify: `src/skytrack_mcp/report/parser.py`
- Create: `src/skytrack_mcp/report/debug_workflow.py`
- Test: `tests/test_report_debug_workflow.py`

**Steps:**
- [ ] Write failing tests in `tests/test_report_debug_workflow.py` proving:
  - `harvest_mission_report_data` in static post-run mode never calls `fetch_live_mavlink_telemetry()` and marks missing telemetry fields as `UNKNOWN` rather than substituting `100.0%` battery.
  - Latest native report selection is strictly scoped to the exact `(project_id, mission_id)` and reports exact `execution_id` and timestamp.
  - User-provided logs/media are labeled `USER_PROVIDED` and never relabeled `NATIVE_CORRELATED`.
- [ ] Update `src/skytrack_mcp/report/parser.py` and implement `src/skytrack_mcp/report/debug_workflow.py`.
- [ ] Register gated read-only report/debug inspection tools on FastMCP and verify tests pass.

---

### Task 3 (Phase 4): Pinned Autonomy SDK Validator, Nadir Camera Projection & Spray Geometry

**Files:**
- Modify: `src/skytrack_mcp/autonomy_sdk.py`
- Create: `src/skytrack_mcp/autonomy/perception_geometry.py`
- Test: `tests/test_perception_and_sdk.py`

**Steps:**
- [ ] Write failing tests in `tests/test_perception_and_sdk.py` catching:
  - Missing `Detector` wiring in Level 4 template.
  - Wrong import sources (`Detector`, `Sprayer` must come from `skytrack_autonomy`; `CameraSense`, `VideoRecorder`, `Snapshot`, `boot_drone` from `local_planner`).
  - Unbounded detector waits or missing frame sequence (`CameraSense.seq` / `Detector.count`) correlation.
  - Nadir pixel bounding box `[u1, v1, u2, v2]` to world ENU polygon projection (`east, north = pose.y, pose.x`, optical offset `+0.125m` north, `-0.01m` z, $H = -\text{pose.z} + 0.217$) and spray width ($0.536 \cdot H$) / dosage ($1.0\text{--}3.0\text{ ml/m}^2$).
  - Organizer model artifact verification (`det-h2026-v26n-b-fp32-640`, ZIP SHA-256 `18e86fda...`, ONNX SHA-256 `6352161d...`).
- [ ] Implement `src/skytrack_mcp/autonomy/perception_geometry.py` and update `src/skytrack_mcp/autonomy_sdk.py`.
- [ ] Verify all tests in `tests/test_perception_and_sdk.py` pass.

---

### Task 4 (Phase 4b): 2026 Hackathon Semifinal An Giang Rule Pack

**Files:**
- Create: `src/skytrack_mcp/contest/semifinal_2026.py`
- Test: `tests/test_semifinal_2026_pack.py`

**Steps:**
- [ ] Write failing tests in `tests/test_semifinal_2026_pack.py` for:
  - Flight ceiling <= 40m AGL and spray ceiling <= 20m AGL (returning `UNKNOWN` when terrain elevation is unavailable).
  - 5m residential boundary buffer check, allowing entry ONLY for approach/landing at CS1 `(0.00, 0.00, 0.0)`, CS2 `(329.32, -234.73, -1.0)`, CS3 `(356.43, -654.32, 0.0)`, CS4 `(41.72, -582.67, -1.1)` within 3.0m touchdown radius, and ALWAYS prohibiting spray within residential areas or buffers.
  - 15-minute per-charge flight limit, 90-minute total mission limit, and Mission Break + manual user resume requirement.
  - Semifinal output report schema status reported as `UNKNOWN` until verified by a native report.
- [ ] Implement `src/skytrack_mcp/contest/semifinal_2026.py` and verify all tests pass.

---

### Task 5 (Phase 5): Global Claude Code Plugin & Portable Launcher Packaging

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `bin/skytrack-mcp-launcher.sh`
- Modify: `.claude/skills/skytrack/SKILL.md`
- Create: `skills/skytrack/SKILL.md`
- Test: `tests/test_plugin_packaging.py`

**Steps:**
- [ ] Write failing tests in `tests/test_plugin_packaging.py` verifying:
  - `.claude-plugin/plugin.json` is valid and contains no hardcoded `/Users/...` paths.
  - `bin/skytrack-mcp-launcher.sh` resolves `skytrack-mcp` across macOS and Linux.
  - `skills/skytrack/SKILL.md` supports natural-language discovery and optional `/skytrack` invocation, with no unsafe automatic hooks.
- [ ] Create plugin manifest, launcher, and skill files, and verify all tests pass.
