# Report Evidence Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make harvested mission reports and requirement verdicts execution-scoped, prevent current telemetry or mission-wide media from masquerading as flight evidence, and preserve `UNKNOWN` wherever the current report format cannot prove a requirement.

**Architecture:** Resolve and expose the selected execution once in the report parser; derive execution-scoped capture/payload evidence only from that non-synthetic entry and separately label live telemetry and mission-folder media inventory. Keep the public read/verify signatures unchanged and make the verifier consume explicit evidence fields, applying the approved three-state aggregate policy.

**Tech Stack:** Python 3.10+, existing JSON/pathlib and standard-library validation, Pydantic v2 models, pytest. No new image-decoding dependency or producer-side report contract.

**Spec:** `docs/superpowers/specs/2026-09-27-skytrack-release-evidence-design.md` §§2, 4–7.

## Global Constraints

- All tests use temporary directories, fixtures, and mocks; none start containers or call live flight endpoints.
- Do not change mission serialization, GCS action translation, the collision-freedom evidence contract, or producer-side event formats.
- `report_provenance == "authentic"` remains the current filename/record matching heuristic, not cryptographic attestation. Keep file-level provenance separate from selected-entry synthetic eligibility.
- A live MAVLink reading is a current snapshot, not terminal evidence for a selected execution unless explicit source correlation and terminal evidence are present.
- Do not synthesize `COMPLETED`, `100%`, `ON_GROUND`, `HOLD`, or disarmed state from missing data.
- Mission-folder captures remain an unattributed inventory; an absent or incomplete event stream is not proof of a capture/payload shortfall.
- Battery comparison remains inclusive `>=` with the existing configured/default threshold; only finite 0–100 execution-correlated terminal values can be evaluated.
- Do not merge, tag, or release without passing CI and mission-linked native execution evidence; this work does not produce flight evidence. Keep PR #1 draft.

## Review Focus

1. A selected later entry is synthetic while an earlier entry appears native → selected-execution evidence is unavailable and cannot pass verification.
2. Requested or implicit latest entry lacks its own status/metadata while top-level metadata exists → no uncorrelated top-level execution facts leak into the selected result.
3. Current telemetry is disconnected, missing fields, invalid, or unrelated to the execution → snapshot remains display-only and evidence verdicts remain `UNKNOWN`.
4. A capture path is absolute/traversing, duplicate, empty, unsupported, corrupt, or stale → it is excluded from execution capture evidence, without promoting the folder inventory as a fallback.
5. Payload streams mix `PAYLOAD_TRIGGER` and `BALL_DROP` without a shared identifier, or contain too few events without an approved completeness signal → return `UNKNOWN`, not a fabricated count or verified `FAIL`.

---

### Task 1: Scope harvested status and metadata to the selected execution

**Files:**
- Modify: `src/skytrack_mcp/report/parser.py:is_synthetic_report`, `find_authentic_report_file`, `harvest_mission_report_data`, `render_markdown_flight_report`
- Modify: `src/skytrack_mcp/clients/docker_exec.py:fetch_live_mavlink_telemetry`
- Test: `tests/test_report_landing.py`, `tests/test_hackathon_benchmark.py`

**Interfaces:**
- `harvest_mission_report_data(..., execution_id=None)` preserves its signature and adds `execution_id` containing the resolved selected entry ID (or `None` when no entry is available).
- `execution_status` comes only from the selected entry: prefer `status_summary.final_status`, then the entry's own `status`, otherwise `"UNKNOWN"`. Duration and world come only from the selected entry's `status_summary.duration_seconds`/`status_summary.world` or an explicitly execution-scoped field on that entry. Vehicle is available only if an explicit field exists on that selected entry or its summary; otherwise it is `None`. Never substitute top-level metadata or mission-plan values as execution facts.
- `telemetry_state` remains a displayable current snapshot and includes `provenance: "current_snapshot"`; `observed_at` is copied only if the telemetry source supplied it. Missing landed/mode values are `"UNKNOWN"`; missing armed/battery values are `None`.
- Separate file-level synthetic checks (filename and `execution_metadata`) from entry-level signatures. Select the execution entry before applying entry-level checks, so a synthetic marker on another entry cannot disqualify this one. Emit `selected_execution_is_synthetic` (`true`/`false`/`null`) and `execution_evidence_available` (true only for an authentic-file, identified, non-synthetic selected entry). A selected synthetic entry is ineligible for execution evidence.
- Emit `terminal_battery_evidence: null` for current report formats. Its normalized shape, if a future confirmed source is added, is `{"execution_id": str, "percentage": float, "terminal": true}`; harvest-time telemetry is never copied into this field.

- [ ] **Step 1: Add failing tests for selected ID, status isolation, and neutral snapshot values**

```python
def _write_native_mission(tmp_path, report, capture_files=None):
    import json

    mission = tmp_path / "prj-P1" / "mis-M1"
    mission.mkdir(parents=True)
    (mission / "mission.json").write_text(
        json.dumps({"world": "urban", "vehicle": "x500_tennis_balls"}), encoding="utf-8"
    )
    (mission / "plan.json").write_text(
        json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}), encoding="utf-8"
    )
    (mission / "skytrack-mission-report.json").write_text(json.dumps(report), encoding="utf-8")
    captures = mission / "media" / "captures"
    for name, content in (capture_files or {}).items():
        target = captures / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return mission


def test_harvest_uses_selected_entry_status_and_id(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    report = {
        "execution_metadata": {
            "mission_id": "M1", "status": "COMPLETED", "duration": 99,
            "world": "top-level-world", "vehicle": "top-level-vehicle",
        },
        "execution_report": [
            {"execution_id": "E1", "status_summary": {"final_status": "Failed"}, "execution_events": []},
            {"execution_id": "E2", "status_summary": {}, "execution_events": []},
        ],
    }
    _write_native_mission(tmp_path, report)
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = parser.harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path, execution_id="E2")
    assert result["execution_id"] == "E2"
    assert result["execution_status"] == "UNKNOWN"
    assert result["execution_duration_s"] is None
    assert result["world"] is None
    assert result["vehicle"] is None
```

Use `_write_native_mission()` for these report fixtures. Add a disconnected-telemetry assertion that absent battery/armed are `None`, landed/mode are `UNKNOWN`, `observed_at` is absent, and snapshot provenance is `current_snapshot`; verify Markdown renders those observations as unavailable. Add a latest-entry case asserting the last entry's ID is emitted. Add two multi-entry cases: one whose selected entry alone has an entry-level synthetic signature (assert the selected ID remains visible, `selected_execution_is_synthetic is True`, `execution_evidence_available is False`, and no selected-entry facts can establish verification evidence), and one whose non-selected entry alone has a synthetic signature (assert the selected authentic entry remains eligible).

- [ ] **Step 2: Run the new harvest tests and confirm they fail on the old defaults**

Run: `pytest -q tests/test_report_landing.py -k 'selected_entry_status_and_id or neutral_snapshot or latest_execution_id'`
Expected: FAIL because the current report omits the resolved ID and inherits top-level/default telemetry values.

- [ ] **Step 3: Implement selected-entry facts and entry-level synthetic classification**

Split `is_synthetic_report()` into file-level checks (filename and top-level execution metadata) and checks against an explicitly supplied selected entry, while retaining its current one-argument call behavior for existing callers. Keep the existing file-level synthetic checks for `synthetic-`/`mock-` filenames and top-level `execution_metadata.provenance`/`source`. Apply selected-entry synthetic checks only to the selected entry: summary provenance `synthetic`, presence of `actions_defined`, `min_ground_speed == 0.002`, or a navigation event whose status starts with `Navigating to WP `. In `find_authentic_report_file()`, apply only file-level checks when selecting the file. Select the requested entry or the existing latest entry, then classify that selected entry separately; do not silently substitute an earlier entry when the requested/latest entry is synthetic, and do not let a non-selected entry's signature affect its eligibility. In harvesting, emit `report_provenance` for the file separately from `selected_execution_is_synthetic` and `execution_evidence_available`. Set status to `UNKNOWN` when selected status is absent; use only selected-entry-correlated duration/world/vehicle values; do not use top-level status/duration/world/vehicle or mission-plan values as substitutes. Keep existing fields but make unavailable execution values `None`; initialize `execution_duration_s` and `terminal_battery_evidence` to `None` because no confirmed source exists. Preserve `read_uav_python_logs()` behavior. In `fetch_live_mavlink_telemetry()`, preserve explicit false values but do not default missing `is_armed` to false, and pass through `observed_at` only if returned by the telemetry source. In the report's `telemetry_state`, set `provenance: "current_snapshot"` and copy `observed_at` only when present; never use the report-generation timestamp as the sample time.

- [ ] **Step 4: Render snapshot/unavailable labels and run report-parser regressions**

Update Markdown so the selected execution ID and current-snapshot provenance are explicit and absent values read as unavailable, not as a percentage or measured flight state. Keep mission-folder captures labeled as inventory. Run: `pytest -q tests/test_report_landing.py tests/test_hackathon_benchmark.py::test_report_parser_distinguishes_synthetic_vs_authentic`
Expected: PASS; add/retain a case where only a later selected entry has synthetic signatures and verify it is not treated as authentic execution evidence.

### Task 2: Derive safe execution-scoped capture evidence

**Files:**
- Modify: `src/skytrack_mcp/report/parser.py:harvest_mission_report_data`
- Test: `tests/test_report_landing.py`

**Interfaces:**
- Preserve `media_output.captures` and `captures_count` as an explicitly unattributed mission-folder inventory.
- Add `execution_captures` and nullable `execution_captures_count` for the selected non-synthetic entry only. A missing or unusable execution capture reference yields `None` count, not zero.
- Use the observed native capture representation `PAYLOAD_TRIGGER` with `data.action == "CAPTURE_IMAGE"` and `data.filename`; accept only `.jpg`/`.jpeg`, `.png`, and `.webp` with matching JPEG/PNG/WebP signatures. This is a dependency-free signature check, not full image decoding.

- [ ] **Step 1: Add failing capture-link tests**

```python
def test_capture_evidence_uses_only_selected_execution_and_deduplicates(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    report = {
        "execution_metadata": {"mission_id": "M1"},
        "execution_report": [
            {
                "execution_id": "E1",
                "status_summary": {"final_status": "Succeeded"},
                "execution_events": [
                    {"event": "PAYLOAD_TRIGGER", "data": {"action": "CAPTURE_IMAGE", "filename": "e1.jpg"}},
                    {"event": "PAYLOAD_TRIGGER", "data": {"action": "CAPTURE_IMAGE", "filename": "./e1.jpg"}},
                ],
            },
            {
                "execution_id": "E2",
                "status_summary": {"final_status": "Succeeded"},
                "execution_events": [
                    {"event": "PAYLOAD_TRIGGER", "data": {"action": "CAPTURE_IMAGE", "filename": "e2.jpg"}},
                ],
            },
        ],
    }
    _write_native_mission(tmp_path, report, {
        "e1.jpg": b"\xff\xd8\xffimage-data",
        "e2.jpg": b"\xff\xd8\xffimage-data",
        "stale.jpg": b"\xff\xd8\xffimage-data",
    })
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = parser.harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path, execution_id="E1")
    assert result["execution_captures"] == ["e1.jpg"]
    assert result["execution_captures_count"] == 1
    assert result["media_output"]["captures_count"] == 3
```

Add cases for no linked event (count is `None`), repeated references, path traversal and absolute paths, symlinks resolving outside the capture directory, empty/corrupt bytes, unsupported extension, and extension/signature mismatch. Pin the supported signatures with concrete fixtures: JPEG `b"\xff\xd8\xffimage-data"`, PNG `b"\x89PNG\r\n\x1a\nimage-data"`, and WebP `b"RIFF\x04\x00\x00\x00WEBP"`; each valid extension/signature pair is accepted and mismatches are rejected. Ensure mission-folder inventory remains visible but never determines execution-scoped count.

- [ ] **Step 2: Run the capture tests and verify they fail before implementation**

Run: `pytest -q tests/test_report_landing.py -k capture_evidence`
Expected: FAIL because the parser currently returns only mission-wide file inventory.

- [ ] **Step 3: Implement constrained reference resolution and signature checks**

Resolve each filename beneath the mission's `media/captures` directory; reject absolute paths, traversal outside that directory, symlinks resolving outside it, non-files, empty files, unsupported extensions, and mismatched signatures. Normalize resolved relative paths before deduplication. Only inspect capture events from the selected, non-synthetic entry. Return a nullable count when there is no usable mapping; do not add a completeness marker.

- [ ] **Step 4: Run capture-attribution and synthetic-entry tests**

Run: `pytest -q tests/test_report_landing.py -k 'capture_evidence or synthetic or selects_matching_execution'`
Expected: PASS, including stale/unlinked inventory staying out of execution evidence.

### Task 3: Preserve payload-event provenance and ambiguity

**Files:**
- Modify: `src/skytrack_mcp/report/parser.py:harvest_mission_report_data`
- Test: `tests/test_report_landing.py`

**Interfaces:**
- Payload verification input is derived only from events in the selected non-synthetic execution.
- Count only selected `BALL_DROP` events and selected `PAYLOAD_TRIGGER` records whose observed producer schema identifies a drop action (currently `data.operation == "drop-ball"`); capture actions such as `data.action == "CAPTURE_IMAGE"` are not payload drops. Deduplicate mixed event types only when a shared action/event ID proves they describe the same drop. If both drop event types occur and available identifiers cannot establish overlap versus distinct drops, mark the payload count unavailable/ambiguous so verification returns `UNKNOWN`.
- No completeness field is invented; absent/incomplete or below-threshold streams do not prove zero drops.

- [ ] **Step 1: Add failing payload-event parsing tests**

The repository's existing `BALL_DROP` and paired simulated `PAYLOAD_TRIGGER` records do not carry a shared action/event ID (see `src/skytrack_mcp/simulation/runner.py`). Do not add a synthetic `action_id` to the fixture or assume timestamp/coordinates establish identity. For backward compatibility, preserve `payload_triggers` as the existing list of selected-entry event `data` objects for display; do not change its shape. Add a nullable `payload_triggers_count` that is `None` for unresolved mixed event kinds or absent selected evidence. Add this conservative ambiguity test using the observed record shapes:

```python
def test_mixed_payload_event_kinds_without_shared_id_are_ambiguous(tmp_path, monkeypatch):
    from skytrack_mcp.report import parser

    report = {
        "execution_metadata": {"mission_id": "M1"},
        "execution_report": [{
            "execution_id": "E1",
            "status_summary": {"final_status": "Succeeded"},
            "execution_events": [
                {"event": "PAYLOAD_TRIGGER", "data": {"operation": "drop-ball", "x": 1, "y": 2}},
                {"event": "BALL_DROP", "data": {"x": 1, "y": 2, "z": 3}},
            ],
        }],
    }
    _write_native_mission(tmp_path, report)
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = parser.harvest_mission_report_data("M1", "P1", client_data_dir=tmp_path, execution_id="E1")
    assert result["payload_triggers_count"] is None
```

Also test sufficient distinct selected events of a single event kind, a `PAYLOAD_TRIGGER` with `data.action == "CAPTURE_IMAGE"` not increasing the payload-drop count, no report/events as unavailable evidence, and a below-threshold count without completeness as unknown. Reuse the fixture's `BALL_DROP` shape for conservative unknown coverage; do not add invented completeness fields to fixture data. A separate future test may exercise ID-based deduplication only if an actual producer schema with a shared identifier is confirmed and cited.

- [ ] **Step 2: Run payload parsing tests and confirm they fail on replacement behavior**

Run: `pytest -q tests/test_report_landing.py -k payload`
Expected: FAIL because the parser currently replaces all `PAYLOAD_TRIGGER` events with `BALL_DROP` events whenever any ball drop exists.

- [ ] **Step 3: Implement selected-event accounting without inventing completeness**

Keep the selected events separate from mission plan actions. Preserve records needed for report display, deduplicate by shared action/event ID when present, and expose `payload_triggers_count` as unavailable when mixed-event overlap is unresolved or selected-event evidence is absent. Do not return a zero count as proof of a shortfall.

- [ ] **Step 4: Run payload and existing native-return regressions**

Run: `pytest -q tests/test_report_landing.py -k 'payload or native_completed_return or selects_matching_execution'`
Expected: PASS; existing landing/takeoff event extraction remains unchanged.

### Task 4: Make verifier require selected-execution evidence

**Files:**
- Modify: `src/skytrack_mcp/report/verification.py:evaluate_mission_requirements`
- Test: `tests/test_server.py`, `tests/test_report_landing.py`

**Interfaces:**
- Gate every requirement based on selected-execution report facts (landing, takeoff altitude, reached waypoints, world, captures, and payload events) on `execution_evidence_available is True`, authentic file provenance, and a resolved selected `execution_id`. A current telemetry snapshot cannot pass or fail a terminal execution requirement. If selected-entry data such as world is absent, that item is `UNKNOWN`, not a mismatch `FAIL`.
- Capture requirements use only `execution_captures_count` from an eligible selected execution. Sufficient valid captures pass; otherwise unavailable/insufficient evidence is `UNKNOWN` because the present report format lacks completeness.
- Payload requirements use only eligible selected-entry payload evidence. Sufficient distinct events pass; insufficient, absent, or ambiguous records are `UNKNOWN` for lack of completeness.
- Battery requirements use only a finite 0–100 terminal battery sample explicitly correlated to the selected `execution_id`. Preserve inclusive `>=` and default 20.0. A harvest-time telemetry snapshot cannot pass or fail battery margin. The current parser has no confirmed terminal sample source, so normal harvest remains `UNKNOWN`; unit tests may supply the explicitly normalized correlated evidence shape to pin threshold behavior.
- Overall verdict: any mandatory verified `FAIL` → `FAIL`; otherwise any mandatory `UNKNOWN` → `UNKNOWN`; at least one mandatory item and all mandatory `PASS` → `PASS`; optional-only nonempty requirements → `UNKNOWN`; empty requirements → `FAIL`. Optional statuses remain visible and do not block mandatory-only success.

- [ ] **Step 1: Add failing evaluator tests for execution evidence and aggregate states**

```python
def test_mandatory_unknown_is_not_collapsed_to_fail():
    result = evaluate_mission_requirements(
        "M1",
        [{"name": "Battery", "type": "battery_margin", "mandatory": True}],
        {"execution_id": "E1", "report_provenance": "authentic", "telemetry_state": {
            "battery_percentage": 98, "provenance": "current_snapshot",
        }},
    )
    assert result.items[0].status == VerificationStatus.UNKNOWN
    assert result.overall_status == VerificationStatus.UNKNOWN
```

Add table-driven tests for mandatory PASS/FAIL/UNKNOWN; optional FAIL/UNKNOWN alongside mandatory PASS; optional-only input; and empty input. Update `test_unit_verification_matrix` so mission inventory captures and snapshot battery alone no longer count as execution evidence. Add evaluator cases where (1) an authentic file has `execution_evidence_available is False` because the selected entry is synthetic and all report-derived requirements (landing, takeoff altitude, waypoints, world, captures, payload) remain `UNKNOWN` even when those fields look positive, (2) connected current telemetry reports `IN_AIR` but a selected report does not prove terminal landing and the landing verdict remains `UNKNOWN`, and (3) an eligible selected execution with no selected world value gets `UNKNOWN`, not a world-mismatch `FAIL`. Add a public-tool regression in `tests/test_report_landing.py` proving the full harvest-to-verifier path cannot use a mission-folder file or current snapshot as selected-execution evidence:

```python
def test_public_verifier_does_not_use_unattributed_capture_or_snapshot_battery(tmp_path, monkeypatch):
    from skytrack_mcp.mcp import tools
    from skytrack_mcp.report import parser

    mission = _write_native_mission(
        tmp_path, {"execution_metadata": {"mission_id": "M1"}},
        {"stale.jpg": b"\xff\xd8\xffimage-data"},
    )
    (mission / "skytrack-mission-report.json").unlink()
    monkeypatch.setattr(tools, "resolve_mission_dir", lambda _: (mission, "P1", "M1"))
    monkeypatch.setattr(
        tools, "harvest_mission_report_data",
        lambda mid, pid, execution_id=None: parser.harvest_mission_report_data(
            mid, pid, client_data_dir=tmp_path, execution_id=execution_id
        ),
    )
    monkeypatch.setattr(parser, "read_uav_python_logs", lambda **_: {"logs": ""})
    monkeypatch.setattr(parser, "fetch_live_mavlink_telemetry", lambda: {
        "connected": False, "battery_percentage": 98.0,
    })

    result = tools.tool_skytrack_verify_mission_requirements(
        requirements=[
            {"name": "Captures", "type": "captures", "expected": 1, "mandatory": True},
            {"name": "Battery", "type": "battery_margin", "expected": 20, "mandatory": True},
        ], mission_id="M1",
    )
    assert result["overall_status"] == "UNKNOWN"
    assert [item["status"] for item in result["items"]] == ["UNKNOWN", "UNKNOWN"]
```

This test uses an actual harvest through the public tool, while mocking only external telemetry/log reads and mission lookup; it must not rely on a caller-supplied report dictionary.

- [ ] **Step 2: Add capture, payload, and battery evidence tests before implementation**

Test that direct-helper input with `report_provenance != "authentic"` cannot PASS captures/payload/battery even if it contains positive counts/values; snapshot-only battery stays `UNKNOWN`; `execution_captures_count is None` and insufficient payload evidence remain `UNKNOWN`; normalized terminal samples with matching selected execution ID pass at exactly the configured threshold and fail below it; `NaN`, infinities, values below 0 or above 100, and execution-ID mismatch yield `UNKNOWN`.

- [ ] **Step 3: Run the focused verifier tests and confirm current behavior fails**

Run: `pytest -q tests/test_server.py -k 'verification_matrix or verification_evidence or aggregate_verdict'`
Expected: FAIL because the verifier currently uses mission inventory/snapshot fields and collapses mandatory `UNKNOWN` to `FAIL`.

- [ ] **Step 4: Implement fail-closed evidence evaluation and explicit aggregate precedence**

Gate execution-derived evidence on `execution_evidence_available is True`, `report_provenance == "authentic"`, and a resolved selected `execution_id`; report file authenticity alone is insufficient when the chosen entry has a synthetic signature. Replace capture and payload branches with nullable execution-scoped fields. Validate that `terminal_battery_evidence` is a dictionary with `terminal is True`, a finite numeric non-boolean `percentage` in 0–100, and an `execution_id` exactly matching the selected report entry before applying the existing inclusive threshold; ignore `telemetry_state.battery_percentage` for verification. Compute overall status using the ordered mandatory failure / mandatory unknown / mandatory pass / optional-only / empty rules above. Update summary wording to say the aggregate status is based on mandatory requirements, while retaining optional item details.

- [ ] **Step 5: Run parser, verifier, and public-tool regressions together**

Run: `pytest -q tests/test_report_landing.py tests/test_server.py tests/test_hackathon_benchmark.py::test_report_parser_distinguishes_synthetic_vs_authentic -m "not live_simulation"`
Expected: PASS, including report-read and requirement-verification calls for stale requested execution IDs.

### Task 5: Run full non-live release checks (not release actions)

**Files:**
- Verify only: `.github/workflows/ci.yml`, `pyproject.toml`

- [ ] **Step 1: Run the full non-live test suite**

Run: `pytest -v -m "not live_simulation"`
Expected: PASS. Do not start a simulator, execute a script, or dispatch a mission.

- [ ] **Step 2: Run critical Ruff checks and package build**

Run: `ruff check --select E9,F63,F7,F82 src tests evals && uv build`
Expected: PASS.

- [ ] **Step 3: Run the installed-wheel smoke test**

Run: `uv venv /tmp/skytrack-report-wheel-smoke && uv pip install --python /tmp/skytrack-report-wheel-smoke/bin/python dist/*.whl && /tmp/skytrack-report-wheel-smoke/bin/python -c 'from skytrack_mcp.report.parser import harvest_mission_report_data; from skytrack_mcp.report.verification import evaluate_mission_requirements; assert callable(harvest_mission_report_data); assert callable(evaluate_mission_requirements)'`
Expected: PASS importing the installed report parser and verifier; no runtime services are contacted.

- [ ] **Step 4: Report release gates accurately**

Report exact commands and outcomes. Do not call fixtures or unit tests native flight evidence; do not merge, tag, or release. CI and mission-linked native execution evidence remain separate requirements, and a capability matrix plus separately designed safeguards for lossy mission editing, unsupported GCS actions, and live dispatch remain outside this plan.
