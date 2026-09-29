# SDF Source Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make world discovery include packaged and runtime worlds, prefer readable runtime SDFs, and report truthful source and runtime-identity provenance wherever world geometry is returned.

**Architecture:** Put runtime/container and packaged-cache SDF resolution in one small world-source module so inspection and route-collision parsing cannot silently choose different files. Keep the existing `read_sdf_content()` string interface and existing not-found exception behavior, while adding provenance to parsed/inspected results and the world-context MCP response.

**Tech Stack:** Python 3.10+, `pathlib`, `subprocess`, existing `defusedxml` parsing, pytest and pytest monkeypatch fixtures. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-27-skytrack-release-evidence-design.md` §§2–3, 6 (SDF tests), 7.

## Global Constraints

- All tests use temporary directories, fixtures, and mocks; none start containers or call live flight endpoints.
- No simulator lifecycle or flight operation is in scope.
- A packaged fallback is never labeled as runtime geometry; packaged selection always has `runtime_world_match: null`.
- Runtime identity metadata describes reported Gazebo/PX4 world names, not byte-for-byte proof of the SDF Gazebo loaded.
- Do not merge, tag, or release without passing CI and mission-linked native execution evidence; this work does not produce flight evidence.
- Keep changes limited to SDF discovery/resolution/provenance and their regression tests; do not include mission serialization, GCS action translation, or dispatch-safety work.

## Review Focus

1. Docker is missing, times out, or the runtime container is stopped while packaged worlds exist → packaged discovery and SDF inspection still work offline.
2. A requested runtime SDF cannot be read while a packaged copy exists → use packaged geometry and report `packaged_cache`, not runtime provenance.
3. Runtime identities are partially available or disagree → match is `false` if any available identity disagrees, `true` only if at least one identity exists and all available identities match, otherwise `null`.
4. Runtime-only world names exist alongside packaged worlds → discovery returns the sorted, deduplicated union.
5. Neither runtime nor packaged SDF exists → preserve each existing public not-found error type and message contract.

---

### Task 1: Centralize SDF discovery and content resolution

**Files:**
- Create: `src/skytrack_mcp/world/sdf_source.py`
- Modify: `src/skytrack_mcp/clients/docker_exec.py:list_gazebo_worlds`, `get_simulation_runtime_config`
- Test: `tests/test_world_sdf_resolution.py`

**Interfaces:**
- Produces `list_available_worlds() -> List[str]`, returning the sorted set union of packaged `.sdf` stems and runtime `.sdf` stems.
- Produces `resolve_sdf_content(world_name: str) -> Tuple[str, str]`, returning `(xml_text, "runtime_container" | "packaged_cache")`. Runtime is tried first; packaged content is the fallback. If neither source has readable content, it raises `FileNotFoundError`; public callers translate that into their existing exception types and message prefixes.
- Runtime discovery and reads use `_list_runtime_worlds() -> List[str]`, `_read_runtime_sdf(world_name: str) -> Optional[str]`, and `_run_cmd(args, timeout)`; Docker failures, timeouts, nonzero status, and empty content make the runtime source unavailable.
- Produces `get_runtime_world_identities() -> Dict[str, Optional[str]]` with independent `gazebo_world` and `px4_world` values. Private readers `_read_gazebo_world_identity()` and `_read_px4_world_identity()` are independently guarded so one unavailable container must not hide a readable identity from the other.
- `docker_exec.list_gazebo_worlds()` delegates to the shared discovery function. `get_simulation_runtime_config()` keeps its current `world` and `vehicle` keys for compatibility and adds both independent world-identity keys.

- [ ] **Step 1: Add failing tests for world-name union and runtime preference**

```python
def test_world_names_are_union_of_packaged_and_runtime(tmp_path, monkeypatch):
    from skytrack_mcp.world import sdf_source

    (tmp_path / "shared.sdf").write_text("packaged", encoding="utf-8")
    (tmp_path / "offline.sdf").write_text("packaged", encoding="utf-8")
    monkeypatch.setattr(sdf_source, "LOCAL_WORLD_CACHE_DIR", tmp_path)
    monkeypatch.setattr(sdf_source, "_list_runtime_worlds", lambda: ["shared", "runtime-only"])

    assert sdf_source.list_available_worlds() == ["offline", "runtime-only", "shared"]
```

Add this runtime-priority test in the same module:

```python
def test_runtime_sdf_precedes_same_named_packaged_file(tmp_path, monkeypatch):
    from skytrack_mcp.world import sdf_source

    (tmp_path / "shared.sdf").write_text("packaged", encoding="utf-8")
    monkeypatch.setattr(sdf_source, "LOCAL_WORLD_CACHE_DIR", tmp_path)
    monkeypatch.setattr(sdf_source, "_read_runtime_sdf", lambda _: "runtime")

    assert sdf_source.resolve_sdf_content("shared") == ("runtime", "runtime_container")
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing shared APIs**

Run: `pytest -q tests/test_world_sdf_resolution.py`
Expected: FAIL because `sdf_source` and its resolver/discovery APIs do not exist yet.

- [ ] **Step 3: Implement the smallest shared discovery/resolution module**

Implement packaged stem discovery, runtime `.sdf` listing, deduplication/sorting, runtime-first content reads, and packaged fallback. Treat Docker executable errors, timeouts, nonzero status, and empty runtime content as runtime unavailability. Keep directory constants in the new module so tests can monkeypatch the source of truth. Add a runtime identity reader that collects Gazebo and PX4 values independently; preserve existing combined `world` semantics in `get_simulation_runtime_config()`.

- [ ] **Step 4: Test fallback, runtime errors, and partial identities**

```python
def test_unavailable_runtime_falls_back_to_packaged_sdf(tmp_path, monkeypatch):
    from skytrack_mcp.world import sdf_source

    (tmp_path / "warehouse.sdf").write_text("<sdf/>\n", encoding="utf-8")
    monkeypatch.setattr(sdf_source, "LOCAL_WORLD_CACHE_DIR", tmp_path)
    monkeypatch.setattr(sdf_source, "_read_runtime_sdf", lambda _: None)

    assert sdf_source.resolve_sdf_content("warehouse") == ("<sdf/>\n", "packaged_cache")
```

Also cover (1) Docker executable missing and command timeout returning packaged names, (2) runtime SDF read failure falling back to the packaged copy, and (3) one available world identity with the other unavailable. For the runtime listing/read tests, monkeypatch the module's subprocess runner to raise `FileNotFoundError` or `subprocess.TimeoutExpired`, and assert packaged results remain available. Pin independent identity collection with:

```python
@pytest.mark.parametrize(
    ("unavailable_reader", "available_reader", "available_value", "expected"),
    [
        ("_read_px4_world_identity", "_read_gazebo_world_identity", "warehouse",
         {"gazebo_world": "warehouse", "px4_world": None}),
        ("_read_gazebo_world_identity", "_read_px4_world_identity", "warehouse",
         {"gazebo_world": None, "px4_world": "warehouse"}),
    ],
)
def test_runtime_world_identity_readers_fail_independently(
    monkeypatch, unavailable_reader, available_reader, available_value, expected
):
    from skytrack_mcp.world import sdf_source

    def unavailable_identity():
        raise FileNotFoundError("runtime container unavailable")

    monkeypatch.setattr(sdf_source, unavailable_reader, unavailable_identity)
    monkeypatch.setattr(sdf_source, available_reader, lambda: available_value)

    assert sdf_source.get_runtime_world_identities() == expected
```

When neither source contains the requested world, assert inspection raises `ValueError` with the existing message prefix `Could not read SDF world '<name>' at`, while `read_sdf_content()` raises `SkyTrackError` with `SkyTrackErrorCode.WORLD_NOT_FOUND` and retains its existing `Could not load SDF world '<name>' from container or cache:` message prefix. Run: `pytest -q tests/test_world_sdf_resolution.py`. Expected: PASS.

### Task 2: Apply common source and identity metadata to both geometry readers

**Files:**
- Modify: `src/skytrack_mcp/clients/docker_exec.py:inspect_world_sdf`
- Modify: `src/skytrack_mcp/world/sdf_parser.py:read_sdf_content`, `parse_world_sdf`
- Test: `tests/test_world_sdf_resolution.py`

**Interfaces:**
- `read_sdf_content(world_name: str) -> str` remains string-returning and resolves from the shared source helper.
- `inspect_world_sdf(...)` and `parse_world_sdf(world_name)` each add `sdf_source` and `runtime_world_match` to their returned dictionaries.
- Runtime match is computed from the requested normalized world name and the independently available runtime identities; packaged source always returns null.

- [ ] **Step 1: Add failing tests for metadata and matching rules**

```python
@pytest.mark.parametrize(
    ("identities", "expected"),
    [
        ({"gazebo_world": "warehouse", "px4_world": "warehouse"}, True),
        ({"gazebo_world": "warehouse", "px4_world": "urban"}, False),
        ({"gazebo_world": "warehouse", "px4_world": None}, True),
        ({"gazebo_world": "urban", "px4_world": None}, False),
        ({"gazebo_world": None, "px4_world": "warehouse"}, True),
        ({"gazebo_world": None, "px4_world": "urban"}, False),
        ({"gazebo_world": None, "px4_world": None}, None),
    ],
)
def test_runtime_sdf_reports_world_identity_match(tmp_path, monkeypatch, identities, expected):
    from skytrack_mcp.clients import docker_exec
    from skytrack_mcp.world import sdf_parser

    from skytrack_mcp.world import sdf_source

    xml = '<sdf><world name="warehouse"/></sdf>'
    monkeypatch.setattr(sdf_source, "resolve_sdf_content", lambda _: (xml, "runtime_container"))
    monkeypatch.setattr(sdf_source, "get_runtime_world_identities", lambda: identities)
    inspected = docker_exec.inspect_world_sdf("warehouse")
    parsed = sdf_parser.parse_world_sdf("warehouse")

    assert inspected["sdf_source"] == parsed["sdf_source"] == "runtime_container"
    assert inspected["runtime_world_match"] is parsed["runtime_world_match"] is expected
```

Add a packaged-fallback case by stubbing `resolve_sdf_content()` to return `(xml, "packaged_cache")`; assert both readers report `sdf_source == "packaged_cache"` and `runtime_world_match is None` even if runtime identity says the requested world is active.

- [ ] **Step 2: Run the focused test and verify result metadata is absent**

Run: `pytest -q tests/test_world_sdf_resolution.py`
Expected: FAIL because inspection and parsed-world dictionaries do not yet include provenance fields.

- [ ] **Step 3: Route both readers through the shared resolver**

Replace the separate packaged-first reads with `resolve_sdf_content()`. Preserve `inspect_world_sdf()`'s `ValueError` on not-found and translate resolver not-found in `read_sdf_content()` into the existing `SkyTrackErrorCode.WORLD_NOT_FOUND`. Keep all geometry parsing behavior unchanged. Add a shared runtime-match calculation and return both fields from `inspect_world_sdf()` and `parse_world_sdf()`.

- [ ] **Step 4: Verify equivalent parser metadata and unchanged geometry behavior**

Run: `pytest -q tests/test_world_sdf_resolution.py tests/test_server.py -k 'world_discovery or urban_mesh or inline_mesh'`
Expected: PASS; obstacle parsing and incomplete-mesh behavior remain unchanged while both parse paths agree on source provenance.

### Task 3: Preserve provenance through the world-context MCP tool

**Files:**
- Modify: `src/skytrack_mcp/mcp/tools.py:340-367`
- Test: `tests/test_server.py`

**Interfaces:**
- `tool_skytrack_get_world_context(world_name: Optional[str] = None)` preserves its existing fields and adds `sdf_source` and `runtime_world_match` from the inspection result.
- `tool_skytrack_inspect_world(...)` already returns the inspection dictionary directly; its new fields must remain intact without changing its signature.

- [ ] **Step 1: Add a failing world-context pass-through test**

```python
def test_world_context_includes_sdf_provenance(monkeypatch):
    from skytrack_mcp.mcp import tools

    monkeypatch.setattr(tools, "inspect_world_sdf", lambda _: {
        "world": "warehouse",
        "spherical_coordinates": {},
        "total_collision_boxes": 0,
        "included_models": [],
        "sdf_source": "runtime_container",
        "runtime_world_match": True,
    })
    result = tools.tool_skytrack_get_world_context("warehouse")
    assert result["sdf_source"] == "runtime_container"
    assert result["runtime_world_match"] is True
```

Use the repository's existing import style for the test; no live Docker call is permitted.

- [ ] **Step 2: Run the targeted test and verify fields are currently dropped**

Run: `pytest -q tests/test_server.py -k world_context_includes_sdf_provenance`
Expected: FAIL because the world-context wrapper currently constructs a reduced dictionary.

- [ ] **Step 3: Add only the two provenance pass-through fields**

Copy `data.get("sdf_source")` and `data.get("runtime_world_match")` into the existing world-context result without changing other fields or triggering runtime state reads.

- [ ] **Step 4: Run the world/tool regression set**

Run: `pytest -q tests/test_world_sdf_resolution.py tests/test_server.py -k 'world_context or world_discovery or urban_mesh or inline_mesh'`
Expected: PASS.

### Task 4: Run package-level offline checks

**Files:**
- Verify only: `.github/workflows/ci.yml`
- Test: focused SDF tests and installed-wheel smoke test

**Interfaces:**
- The installed wheel must continue to find packaged `warehouse.sdf` when Docker is unavailable.

- [ ] **Step 1: Run all SDF resolver tests**

Run: `pytest -q tests/test_world_sdf_resolution.py tests/test_server.py -k 'world_context or world_discovery or urban_mesh or inline_mesh'`
Expected: PASS with all runtime behavior mocked.

- [ ] **Step 2: Run the existing wheel smoke flow after implementation is authorized**

Run: `uv build && uv venv /tmp/skytrack-wheel-smoke && uv pip install --python /tmp/skytrack-wheel-smoke/bin/python dist/*.whl && /tmp/skytrack-wheel-smoke/bin/python -c 'import subprocess; import skytrack_mcp.clients.docker_exec as d; from skytrack_mcp.world import sdf_source as s; s._run_cmd = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "Docker unavailable (smoke-test stub)"); assert "warehouse" in d.list_gazebo_worlds(); result = d.inspect_world_sdf("warehouse"); assert result["world"] == "warehouse"; assert result["sdf_source"] == "packaged_cache"'`
Expected: PASS using installed packaged geometry while Docker calls are stubbed unavailable; no simulation stack is started or required.

- [ ] **Step 3: Check the plan's release boundary**

Do not merge, tag, or release based on these local checks. CI and mission-linked native execution evidence remain independent release gates; no native flight evidence is generated by this plan.
