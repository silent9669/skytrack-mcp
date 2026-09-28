# SkyTrack MCP Read-Only Core and Safety Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cross-platform, read-only SkyTrack MCP core featuring exact project/mission target resolution, session/permission authorization gating (`PERMISSION_UNVERIFIED` fail-safe), cross-platform data-root discovery, and complete exclusion of hazardous flight/control/simulation tools from the default server.

**Architecture:**
1. Exclude all flight dispatch, UAV control, simulation lifecycle, and recovery tools from the default FastMCP registration.
2. Provide platform-agnostic data-root resolution (macOS `~/Library/Application Support/SkyTrack/ClientData`, Linux `$XDG_CONFIG_HOME/SkyTrack/ClientData` or `~/.config/SkyTrack/ClientData`) and platform-agnostic machine ID derivation (Linux `/etc/machine-id` or `/var/lib/dbus/machine-id`, macOS `ioreg`).
3. Implement exact resolution from human-readable project and mission names to stable IDs (`prj-*`, `mis-*`), handle duplicate names with disambiguation errors, require explicit confirmation before creating any missing mission, and prohibit any fallback to "most recent" or hardcoded project IDs.
4. Implement App session and edit-permission verification: verify session identity and edit authorization, treating filesystem writability as insufficient and reporting `PERMISSION_UNVERIFIED` (read-only enforcement) when edit rights are unverified.

**Tech Stack:** Python 3.10+, FastMCP, pytest, asyncio.

**Spec:** `docs/superpowers/specs/2026-09-28-skytrack-agent-workflow-design.md`

## Global Constraints

- Python 3.10+ compatible, strictly offline unit/contract tests without external network or live simulation calls.
- Default MCP server must NEVER register agent-callable flight dispatch (`execute_route_mission`, `execute_uav_python_script`, `run_mission_and_wait_completion`), flight control (`control_uav_flight`), simulation stack lifecycle (`tool_skytrack_simulation_*`, `manage_simulation_stack`), or recovery (`tool_skytrack_recover`).
- No hardcoded developer paths (`/Users/...`) or hardcoded project fallbacks (`01M11QPK1C3Y5GFNBDADS8H7MC`).
- Filesystem writability != SkyTrack edit permission: unverified permission must result in `PERMISSION_UNVERIFIED` and read-only mode.
- Strict isolation from any private Variant B ground truth or evaluator files.

## Review Focus

1. Tool registry leakage: ensure no simulation/flight/control tool is discoverable in `session.list_tools()`.
2. Platform portability: ensure data-root and machine ID discovery work on Linux without `ioreg` or macOS paths.
3. Ambiguity handling: when multiple missions share a name within a project or across projects, resolution must fail with structured candidate details rather than guessing.
4. No silent creation or most-recent fallback: resolving a nonexistent mission or omitting mission ID must error cleanly, never silently selecting `missions[0]` or inventing a project ID.
5. Permission fail-safe: any write attempt when edit authorization is unverified or view-only must be blocked with `PERMISSION_UNVERIFIED`.

---

### Task 1: Safety Boundary — Deregister Hazardous Tools from Default MCP Server

**Files:**
- Modify: `src/skytrack_mcp/server.py`
- Test: `tests/test_safety_boundary.py`
- Modify: `tests/test_mcp_protocol.py`

**Interfaces:**
- Produces: Default FastMCP server with clean read-only/authoring toolset, guaranteed free of `execute_route_mission`, `execute_uav_python_script`, `run_mission_and_wait_completion`, `control_uav_flight`, `tool_skytrack_simulation_*`, `manage_simulation_stack`, `tool_skytrack_recover`.

- [ ] **Step 1: Write failing test in `tests/test_safety_boundary.py`**
Assert that hazardous tool names are NOT registered on `mcp` in `skytrack_mcp.server`.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_safety_boundary.py`
Expected: FAIL showing hazardous tools currently present.

- [ ] **Step 3: Remove hazardous tool registrations in `src/skytrack_mcp/server.py` and update `tests/test_mcp_protocol.py`**
Remove decorator and tool mappings for simulation control, flight execution, and recovery.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_safety_boundary.py tests/test_mcp_protocol.py`
Expected: PASS.

---

### Task 2: Cross-Platform Data-Root and Session Machine ID Discovery

**Files:**
- Create: `src/skytrack_mcp/platform.py`
- Modify: `src/skytrack_mcp/config.py`
- Modify: `src/skytrack_mcp/clients/cloud_client.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `get_default_client_data_dir() -> Path`, `get_machine_id() -> str`.
- Consumes: Standard library `os`, `sys`, `pathlib`, `subprocess`.

- [ ] **Step 1: Write failing test in `tests/test_platform.py`**
Test discovery of ClientData under Darwin (`~/Library/Application Support/SkyTrack/ClientData`) and Linux (`~/.config/SkyTrack/ClientData` or `$XDG_CONFIG_HOME`), and machine ID on Linux (`/etc/machine-id` or fallback) and Darwin (`ioreg`).

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_platform.py`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/skytrack_mcp/platform.py` and wire into `config.py` and `cloud_client.py`**
Implement robust cross-platform path and machine ID discovery.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_platform.py`
Expected: PASS.

---

### Task 3: Exact Project and Mission Target Resolution

**Files:**
- Create: `src/skytrack_mcp/mission/target.py`
- Modify: `src/skytrack_mcp/clients/storage_sync.py`
- Test: `tests/test_target_resolution.py`

**Interfaces:**
- Produces: `resolve_exact_target(client_data_dir: Path, project_name_or_id: Optional[str], mission_name_or_id: Optional[str]) -> TargetResolutionResult`
- Types: `TargetResolutionResult` with status `EXACT`, `AMBIGUOUS`, `MISSING`, `UNAVAILABLE`, with resolved IDs and candidate list.

- [ ] **Step 1: Write failing test in `tests/test_target_resolution.py`**
Test: exact ID match, exact name match, duplicate name error with candidates, missing mission error without creation, and absence of `missions[0]` fallback when omitted.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_target_resolution.py`
Expected: FAIL.

- [ ] **Step 3: Implement `src/skytrack_mcp/mission/target.py` and refactor `storage_sync.py`**
Implement deterministic name/ID resolution without guessing or arbitrary project creation.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_target_resolution.py`
Expected: PASS.

---

### Task 4: App Session and Edit Permission Verification Gate

**Files:**
- Create: `src/skytrack_mcp/session/auth.py`
- Test: `tests/test_session_auth.py`

**Interfaces:**
- Produces: `verify_project_edit_permission(client_data_dir: Path, project_id: str) -> PermissionStatus`
- Enum: `PermissionStatus.VERIFIED`, `PermissionStatus.DENIED`, `PermissionStatus.UNVERIFIED`.
- Rule: Filesystem writability alone never grants `VERIFIED`. Missing or unverified credentials yield `UNVERIFIED` (`PERMISSION_UNVERIFIED`), enforcing read-only operation.

- [ ] **Step 1: Write failing test in `tests/test_session_auth.py`**
Test that writable filesystem without App session metadata returns `UNVERIFIED`; valid project membership with role `editor`/`owner` returns `VERIFIED`; role `viewer` returns `DENIED`.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/test_session_auth.py`
Expected: FAIL.

- [ ] **Step 3: Implement `src/skytrack_mcp/session/auth.py`**
Read session/membership metadata from ClientData/session cache and verify authorization against target project.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/test_session_auth.py`
Expected: PASS.

---

### Task 5: Expose Target & Permission Tools on MCP Server & Run Regression Suite

**Files:**
- Modify: `src/skytrack_mcp/server.py`
- Modify: `src/skytrack_mcp/mcp/tools.py`
- Test: `tests/test_mcp_protocol.py`

**Interfaces:**
- Produces: `tool_skytrack_resolve_target` and `tool_skytrack_check_permission` tools exposed via FastMCP.

- [ ] **Step 1: Add tests in `tests/test_mcp_protocol.py` for target resolution and permission check**
- [ ] **Step 2: Register tools in `server.py` and `tools.py`**
- [ ] **Step 3: Run full offline test suite**
Run: `uv run pytest -k "not live and not simulation"`
Expected: ALL PASS.
