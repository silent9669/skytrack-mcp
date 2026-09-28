"""Unit tests for exact project and mission target resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skytrack_mcp.clients.storage_sync import resolve_mission_dir
from skytrack_mcp.mission.target import (
    TargetResolutionStatus,
    resolve_exact_target,
)


@pytest.fixture
def sample_client_data(tmp_path: Path) -> Path:
    """Create a realistic ClientData tree with multiple projects and missions."""
    # Project 1: Farm Alpha
    p1 = tmp_path / "prj-01M3PRJALPHA00000000000000"
    p1.mkdir(parents=True)
    (p1 / "project.json").write_text(json.dumps({"name": "Farm Alpha", "id": "01M3PRJALPHA00000000000000"}))

    # Mission 1A: Survey North
    m1a = p1 / "mis-01M3MISNORTH00000000000000"
    m1a.mkdir()
    (m1a / "mission.json").write_text(json.dumps({"name": "Survey North", "codeMode": False}))
    (m1a / "plan.json").write_text(json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}))

    # Mission 1B: Shared Name Mission
    m1b = p1 / "mis-01M3MISSHARED1000000000000"
    m1b.mkdir()
    (m1b / "mission.json").write_text(json.dumps({"name": "Pesticide Spray", "codeMode": True}))
    (m1b / "plan.json").write_text(json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}))

    # Project 2: Farm Beta
    p2 = tmp_path / "prj-01M3PRJBETA000000000000000"
    p2.mkdir(parents=True)
    (p2 / "project.json").write_text(json.dumps({"name": "Farm Beta", "id": "01M3PRJBETA000000000000000"}))

    # Mission 2A: Shared Name Mission (Duplicate name across projects)
    m2a = p2 / "mis-01M3MISSHARED2000000000000"
    m2a.mkdir()
    (m2a / "mission.json").write_text(json.dumps({"name": "Pesticide Spray", "codeMode": False}))
    (m2a / "plan.json").write_text(json.dumps({"spawnLocation": [10, 10, 0], "sequences": []}))

    return tmp_path


def test_resolve_exact_by_ids(sample_client_data: Path):
    """Resolving by explicit project_id and mission_id returns EXACT."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id="01M3PRJALPHA00000000000000",
        mission_name_or_id="01M3MISNORTH00000000000000",
    )
    assert res.status == TargetResolutionStatus.EXACT
    assert res.project_id == "01M3PRJALPHA00000000000000"
    assert res.mission_id == "01M3MISNORTH00000000000000"
    assert res.mission_name == "Survey North"


def test_resolve_exact_by_names(sample_client_data: Path):
    """Resolving unique mission name within unique project name returns EXACT."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id="Farm Alpha",
        mission_name_or_id="Survey North",
    )
    assert res.status == TargetResolutionStatus.EXACT
    assert res.project_id == "01M3PRJALPHA00000000000000"
    assert res.mission_id == "01M3MISNORTH00000000000000"


def test_resolve_ambiguous_duplicate_mission_name(sample_client_data: Path):
    """Resolving duplicate mission name across all projects without project scope returns AMBIGUOUS."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id=None,
        mission_name_or_id="Pesticide Spray",
    )
    assert res.status == TargetResolutionStatus.AMBIGUOUS
    assert len(res.candidates) == 2
    assert {c["project_id"] for c in res.candidates} == {
        "01M3PRJALPHA00000000000000",
        "01M3PRJBETA000000000000000",
    }


def test_resolve_disambiguated_by_project(sample_client_data: Path):
    """Providing project name disambiguates a duplicate mission name."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id="Farm Beta",
        mission_name_or_id="Pesticide Spray",
    )
    assert res.status == TargetResolutionStatus.EXACT
    assert res.project_id == "01M3PRJBETA000000000000000"
    assert res.mission_id == "01M3MISSHARED2000000000000"


def test_resolve_missing_mission_does_not_silently_create(sample_client_data: Path):
    """A missing mission returns MISSING and does not create directories or files."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id="Farm Alpha",
        mission_name_or_id="Nonexistent Mission",
        allow_create=False,
    )
    assert res.status == TargetResolutionStatus.MISSING
    assert not (sample_client_data / "prj-01M3PRJALPHA00000000000000" / "mis-Nonexistent Mission").exists()


def test_resolve_empty_mission_errors_without_most_recent_fallback(sample_client_data: Path):
    """Omitting mission ID or passing None must NOT fall back to missions[0]."""
    res = resolve_exact_target(
        client_data_dir=sample_client_data,
        project_name_or_id=None,
        mission_name_or_id=None,
    )
    assert res.status == TargetResolutionStatus.MISSING
    assert "No mission specified" in res.error_message


def test_storage_sync_resolve_mission_dir_rejects_missing_without_fallback(sample_client_data: Path):
    """resolve_mission_dir must raise ValueError if mission_id is omitted or project_id is missing."""
    with pytest.raises(ValueError, match="Explicit mission_id is required"):
        resolve_mission_dir(mission_id=None, client_data_dir=sample_client_data)

    with pytest.raises(ValueError, match="Cannot create mission without an explicit project_id"):
        resolve_mission_dir(
            mission_id="nonexistent-mis",
            client_data_dir=sample_client_data,
            project_id=None,
            create_if_missing=True,
        )


def test_real_world_sanitized_client_data_without_names(tmp_path: Path):
    """Real ClientData has 0 project.json files and mission.json has no 'name' field.

    1. Resolving by exact IDs on disk works without any name metadata.
    2. Resolving by human name without catalog returns UNAVAILABLE.
    3. Resolving by human name with authoritative catalog returns EXACT.
    """
    prj = tmp_path / "prj-01M3KN5YRKHFPRFW72EVKASXCK"
    prj.mkdir(parents=True)
    # Note: NO project.json created (matches real ClientData audit)

    mis = prj / "mis-01M3KVQ2A4ZBAYVF8MBRH3EE8A"
    mis.mkdir(parents=True)
    # Real mission.json shape: codeMode, world, vehicle, etc. NO 'name' field!
    (mis / "mission.json").write_text(
        json.dumps(
            {
                "codeMode": False,
                "world": {"name": "angiang"},
                "vehicle": {"name": "x500_spray"},
            }
        )
    )

    # 1. Exact ID resolution succeeds on disk without name metadata
    res_id = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="01M3KN5YRKHFPRFW72EVKASXCK",
        mission_name_or_id="01M3KVQ2A4ZBAYVF8MBRH3EE8A",
    )
    assert res_id.status == TargetResolutionStatus.EXACT
    assert res_id.project_id == "01M3KN5YRKHFPRFW72EVKASXCK"
    assert res_id.mission_id == "01M3KVQ2A4ZBAYVF8MBRH3EE8A"

    # 2. Resolving by human name without catalog returns UNAVAILABLE
    res_no_cat = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="An Giang Farmland",
        mission_name_or_id="Plot Survey Run",
    )
    assert res_no_cat.status == TargetResolutionStatus.UNAVAILABLE
    assert "catalog is unavailable" in res_no_cat.error_message.lower()

    # 3. Resolving with authoritative catalog resolves names to exact IDs
    def mock_catalog(_root):
        return [
            {
                "project_id": "01M3KN5YRKHFPRFW72EVKASXCK",
                "project_name": "An Giang Farmland",
                "mission_id": "01M3KVQ2A4ZBAYVF8MBRH3EE8A",
                "mission_name": "Plot Survey Run",
            }
        ]

    res_with_cat = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="An Giang Farmland",
        mission_name_or_id="Plot Survey Run",
        catalog_provider=mock_catalog,
    )
    assert res_with_cat.status == TargetResolutionStatus.EXACT
    assert res_with_cat.project_id == "01M3KN5YRKHFPRFW72EVKASXCK"
    assert res_with_cat.mission_id == "01M3KVQ2A4ZBAYVF8MBRH3EE8A"


def test_duplicate_mission_id_across_projects_names_keyed_by_project_and_mission(tmp_path: Path):
    """When two projects share the same mission ID, the catalog provider must not overwrite names."""
    p1 = tmp_path / "prj-01M3PRJONE0000000000000000"
    p1.mkdir(parents=True)
    m1 = p1 / "mis-01M3COMMONID00000000000000"
    m1.mkdir(parents=True)
    (m1 / "mission.json").write_text(json.dumps({"codeMode": False}))

    p2 = tmp_path / "prj-01M3PRJTWO0000000000000000"
    p2.mkdir(parents=True)
    m2 = p2 / "mis-01M3COMMONID00000000000000"
    m2.mkdir(parents=True)
    (m2 / "mission.json").write_text(json.dumps({"codeMode": False}))

    def mock_catalog(_root):
        return [
            {
                "project_id": "01M3PRJONE0000000000000000",
                "project_name": "Project One",
                "mission_id": "01M3COMMONID00000000000000",
                "mission_name": "Alpha Recon",
            },
            {
                "project_id": "01M3PRJTWO0000000000000000",
                "project_name": "Project Two",
                "mission_id": "01M3COMMONID00000000000000",
                "mission_name": "Beta Survey",
            },
        ]

    # Resolve Alpha Recon in Project One
    res1 = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="Project One",
        mission_name_or_id="Alpha Recon",
        catalog_provider=mock_catalog,
    )
    assert res1.status == TargetResolutionStatus.EXACT
    assert res1.project_id == "01M3PRJONE0000000000000000"
    assert res1.mission_id == "01M3COMMONID00000000000000"

    # Resolve Beta Survey in Project Two (ensuring later entry did not overwrite Alpha Recon)
    res2 = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="Project Two",
        mission_name_or_id="Beta Survey",
        catalog_provider=mock_catalog,
    )
    assert res2.status == TargetResolutionStatus.EXACT
    assert res2.project_id == "01M3PRJTWO0000000000000000"
    assert res2.mission_id == "01M3COMMONID00000000000000"


def test_fetch_cloud_mission_catalog_pagination_above_20(tmp_path: Path):
    """Verify fetch_cloud_mission_catalog paginates projects and fetches detail missions."""
    from skytrack_mcp.mission.target import fetch_cloud_mission_catalog

    def fake_api(endpoint, method="GET", params=None, client_data_dir=None):
        if endpoint == "/api/v1/projects":
            offset = params.get("offset", 0)
            if offset == 0:
                return {
                    "data": [
                        {"id": f"01M3PRJ{i:02d}000000000000000", "name": f"Project {i}", "totalMissions": 1}
                        for i in range(20)
                    ]
                }
            elif offset == 20:
                return {
                    "data": [
                        {"id": f"01M3PRJ{i:02d}000000000000000", "name": f"Project {i}", "totalMissions": 1}
                        for i in range(20, 25)
                    ]
                }
            return {"data": []}

        if endpoint.startswith("/api/v1/projects/"):
            pid = endpoint.rsplit("/", 1)[-1]
            p_idx = pid[7:9]
            return {
                "data": {
                    "missions": [
                        {"id": f"01M3MIS{p_idx}000000000000000", "name": f"Mission for {p_idx}", "projectId": pid}
                    ]
                }
            }

        raise ValueError(f"Unexpected endpoint: {endpoint}")

    catalog = fetch_cloud_mission_catalog(client_data_dir=tmp_path, api_caller=fake_api)
    assert len(catalog) == 25
    assert catalog[0]["mission_name"] == "Mission for 00"
    assert catalog[24]["mission_name"] == "Mission for 24"


def test_fetch_cloud_mission_catalog_k6_schema_mapping(tmp_path: Path):
    """Verify project details mapping pattern where projectId/projectName is associated."""
    from skytrack_mcp.mission.target import fetch_cloud_mission_catalog

    def fake_api(endpoint, method="GET", params=None, client_data_dir=None):
        if endpoint == "/api/v1/projects":
            offset = params.get("offset", 0)
            if offset == 0:
                return {"data": [{"id": "01M3PRJNESTED00000000000", "name": "Nested Farm", "totalMissions": 1}]}
            return {"data": []}
        if endpoint == "/api/v1/projects/01M3PRJNESTED00000000000":
            return {
                "data": {
                    "missions": [
                        {
                            "id": "01M3MISNESTED000000000000",
                            "name": "Nested Survey",
                            "projectId": "01M3PRJNESTED00000000000",
                        }
                    ]
                }
            }
        raise ValueError(f"Unexpected endpoint: {endpoint}")

    catalog = fetch_cloud_mission_catalog(client_data_dir=tmp_path, api_caller=fake_api)
    assert len(catalog) == 1
    assert catalog[0]["project_id"] == "01M3PRJNESTED00000000000"
    assert catalog[0]["project_name"] == "Nested Farm"
    assert catalog[0]["mission_id"] == "01M3MISNESTED000000000000"
    assert catalog[0]["mission_name"] == "Nested Survey"


def test_fetch_cloud_mission_catalog_error_propagates_to_unavailable(tmp_path: Path):
    """When catalog provider raises network/auth error, resolve_exact_target must return UNAVAILABLE, never MISSING."""
    prj = tmp_path / "prj-01M3PRJFAIL000000000000000"
    prj.mkdir(parents=True)
    mis = prj / "mis-01M3MISFAIL000000000000000"
    mis.mkdir(parents=True)
    (mis / "mission.json").write_text(json.dumps({"codeMode": False}))

    def failing_catalog(_root):
        raise ConnectionError("SkyTrack BFF unreachable")

    res = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="Some Project Name",
        mission_name_or_id="Some Mission Name",
        catalog_provider=failing_catalog,
    )
    assert res.status == TargetResolutionStatus.UNAVAILABLE
    assert "authoritative skytrack catalog provider failed" in res.error_message.lower()


def test_catalog_provider_failure_with_forged_local_names_returns_unavailable(tmp_path: Path):
    """When authoritative catalog fails, forged/stale local mission.json names must NOT return EXACT."""
    prj = tmp_path / "prj-01M3PRJFORGED0000000000000"
    prj.mkdir(parents=True)
    (prj / "project.json").write_text(json.dumps({"name": "Forged Project"}))

    mis = prj / "mis-01M3MISFORGED0000000000000"
    mis.mkdir(parents=True)
    (mis / "mission.json").write_text(json.dumps({"name": "Forged Mission", "codeMode": False}))

    def failing_catalog(_root):
        raise RuntimeError("BFF HTTP 401 Unauthorized")

    # Human name query must return UNAVAILABLE, NOT EXACT!
    res = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="Forged Project",
        mission_name_or_id="Forged Mission",
        catalog_provider=failing_catalog,
    )
    assert res.status == TargetResolutionStatus.UNAVAILABLE

    # When authoritative catalog fails, even exact ID queries fail closed to UNAVAILABLE
    # to avoid confirming existence or leaking paths of other-account cache dirs.
    res_id = resolve_exact_target(
        client_data_dir=tmp_path,
        project_name_or_id="01M3PRJFORGED0000000000000",
        mission_name_or_id="01M3MISFORGED0000000000000",
        catalog_provider=failing_catalog,
    )
    assert res_id.status == TargetResolutionStatus.UNAVAILABLE


def test_fetch_cloud_mission_catalog_malformed_item_raises(tmp_path: Path):
    """Malformed items missing required fields must raise ValueError rather than being silently dropped."""
    from skytrack_mcp.mission.target import fetch_cloud_mission_catalog

    def fake_api(endpoint, method="GET", params=None, client_data_dir=None):
        if endpoint == "/api/v1/projects":
            offset = params.get("offset", 0)
            if offset == 0:
                return {"data": [{"id": "01M3PRJTEST00000000000000", "name": "Test Project", "totalMissions": 1}]}
            return {"data": []}
        if endpoint == "/api/v1/projects/01M3PRJTEST00000000000000":
            # Missing name to trigger ValueError
            return {"data": {"missions": [{"id": "01M3MISBROKEN000000000000"}]}}
        raise ValueError(f"Unexpected endpoint: {endpoint}")

    with pytest.raises(ValueError, match="missing id or name"):
        fetch_cloud_mission_catalog(client_data_dir=tmp_path, api_caller=fake_api)


def test_authenticated_catalog_isolates_local_stale_orphan_directories(tmp_path: Path):
    """When authoritative catalog succeeds, local orphan directories from other accounts must NOT leak."""
    from skytrack_mcp.mission.target import list_project_and_mission_catalog

    # 1. Real active mission on disk
    active_prj = tmp_path / "prj-01M3ACTIVEPRJ000000000000"
    active_prj.mkdir(parents=True)
    active_mis = active_prj / "mis-01M3ACTIVEMIS000000000000"
    active_mis.mkdir(parents=True)
    (active_mis / "mission.json").write_text(json.dumps({"codeMode": False}))

    # 2. Orphan stale cache on disk from a prior account
    orphan_prj = tmp_path / "prj-01M3ORPHANPRJ000000000000"
    orphan_prj.mkdir(parents=True)
    orphan_mis = orphan_prj / "mis-01M3ORPHANMIS000000000000"
    orphan_mis.mkdir(parents=True)
    (orphan_mis / "mission.json").write_text(json.dumps({"codeMode": False}))

    # 3. Active catalog provider returns only active mission + 1 uncached cloud mission
    def active_catalog(_root):
        return [
            {
                "project_id": "01M3ACTIVEPRJ000000000000",
                "project_name": "Active Farm",
                "mission_id": "01M3ACTIVEMIS000000000000",
                "mission_name": "Active Survey",
            },
            {
                "project_id": "01M3ACTIVEPRJ000000000000",
                "project_name": "Active Farm",
                "mission_id": "01M3UNCACHED000000000000",
                "mission_name": "Cloud Only Survey",
            },
        ]

    catalog, failed = list_project_and_mission_catalog(
        client_data_dir=tmp_path,
        catalog_provider=active_catalog,
    )
    assert failed is False
    assert len(catalog) == 2
    listed_mis_ids = {m["mission_id"] for m in catalog}
    assert "01M3ACTIVEMIS000000000000" in listed_mis_ids
    assert "01M3UNCACHED000000000000" in listed_mis_ids
    # Crucial: orphan stale mission must NOT appear in the user's authenticated catalog!
    assert "01M3ORPHANMIS000000000000" not in listed_mis_ids


def test_commands_secret_sentinel_never_leaks_in_errors(tmp_path: Path):
    """Malformed mission payload containing sensitive commands must NOT leak commands in error string."""
    from skytrack_mcp.mission.target import fetch_cloud_mission_catalog

    secret_sentinel = "SECRET_SUPER_SENSITIVE_SENTINEL_XYZ_123"

    def fake_api(endpoint, method="GET", params=None, client_data_dir=None):
        if endpoint == "/api/v1/projects":
            offset = params.get("offset", 0)
            if offset == 0:
                return {"data": [{"id": "01M3PRJTEST00000000000000", "name": "Test Project", "totalMissions": 1}]}
            return {"data": []}
        if endpoint == "/api/v1/projects/01M3PRJTEST00000000000000":
            # Missing name to trigger ValueError, but includes sensitive commands
            return {
                "data": {
                    "missions": [
                        {
                            "id": "01M3MISTEST00000000000000",
                            "commands": {"payload_auth_token": secret_sentinel},
                        }
                    ]
                }
            }
        raise ValueError(f"Unexpected endpoint: {endpoint}")

    with pytest.raises(ValueError) as exc_info:
        fetch_cloud_mission_catalog(client_data_dir=tmp_path, api_caller=fake_api)

    err_text = str(exc_info.value)
    assert secret_sentinel not in err_text
    assert "missing id or name" in err_text


def test_duplicate_page_stalled_loop_raises_error(tmp_path: Path):
    """When a server repeats the same page of projects indefinitely, pagination raises ValueError."""
    from skytrack_mcp.mission.target import fetch_cloud_mission_catalog

    def fake_api(endpoint, method="GET", params=None, client_data_dir=None):
        if endpoint == "/api/v1/projects":
            return {"data": [{"id": "01M3PRJSTUCK0000000000000", "name": "Stuck Project"}]}
        raise ValueError(f"Unexpected endpoint: {endpoint}")

    with pytest.raises(ValueError, match="Catalog pagination stalled"):
        fetch_cloud_mission_catalog(client_data_dir=tmp_path, api_caller=fake_api)


def test_uncached_mission_read_tools_return_artifact_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When a mission is in authenticated catalog but not cached on disk, read tools return structured ARTIFACT_NOT_CACHED."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp import tools
    from skytrack_mcp.server import get_mission_state

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)

    # Active catalog confirms mission belongs to user's account, but it's not downloaded to disk
    def active_catalog(_root):
        return [
            {
                "project_id": "01M3PRJTEST00000000000000",
                "project_name": "Test Project",
                "mission_id": "01M3UNCACHED000000000000",
                "mission_name": "Uncached Mission",
            }
        ]

    monkeypatch.setattr(tools, "_DEFAULT_CATALOG_PROVIDER", active_catalog)

    res_json = tools.tool_skytrack_get_mission_json("01M3UNCACHED000000000000", project_id="01M3PRJTEST00000000000000")
    assert res_json["status"] == "ARTIFACT_NOT_CACHED"
    assert "open the mission in skytrack desktop" in res_json["message"].lower()

    res_open = tools.tool_skytrack_open_mission("01M3UNCACHED000000000000", project_id="01M3PRJTEST00000000000000")
    assert res_open["status"] == "ARTIFACT_NOT_CACHED"

    res_val = tools.tool_skytrack_validate_mission("01M3UNCACHED000000000000", project_id="01M3PRJTEST00000000000000")
    assert res_val["status"] == "ARTIFACT_NOT_CACHED"
    assert res_val["valid"] is False

    res_state = get_mission_state("01M3UNCACHED000000000000", project_id="01M3PRJTEST00000000000000")
    assert res_state["status"] == "ARTIFACT_NOT_CACHED"


def test_duplicate_mission_id_across_projects_scoped_by_project_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Two projects on disk sharing a mission ID are disambiguated by project_id."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp.tools import tool_skytrack_get_mission_json

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    monkeypatch.setenv("SKYTRACK_OFFLINE_PROFILE", "1")

    p1 = tmp_path / "prj-01M3PRJONE0000000000000000"
    p1.mkdir(parents=True)
    m1 = p1 / "mis-01M3COMMONID00000000000000"
    m1.mkdir(parents=True)
    (m1 / "mission.json").write_text(json.dumps({"targetSpeed": 5.0, "codeMode": False}))

    p2 = tmp_path / "prj-01M3PRJTWO0000000000000000"
    p2.mkdir(parents=True)
    m2 = p2 / "mis-01M3COMMONID00000000000000"
    m2.mkdir(parents=True)
    (m2 / "mission.json").write_text(json.dumps({"targetSpeed": 9.0, "codeMode": False}))

    # Reading with project_id="01M3PRJONE0000000000000000" gets Project 1
    res1 = tool_skytrack_get_mission_json("01M3COMMONID00000000000000", project_id="01M3PRJONE0000000000000000")
    assert res1["project_id"] == "01M3PRJONE0000000000000000"
    assert res1["mission"]["targetSpeed"] == 5.0

    # Reading with project_id="01M3PRJTWO0000000000000000" gets Project 2
    res2 = tool_skytrack_get_mission_json("01M3COMMONID00000000000000", project_id="01M3PRJTWO0000000000000000")
    assert res2["project_id"] == "01M3PRJTWO0000000000000000"
    assert res2["mission"]["targetSpeed"] == 9.0

    # Reading without project_id raises ValueError ambiguity
    with pytest.raises(ValueError, match="Duplicate mission ID|Ambiguous mission_id"):
        tool_skytrack_get_mission_json("01M3COMMONID00000000000000")


def test_catalog_auth_failure_does_not_emit_orphan_ids_in_list_missions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When catalog provider fails, tool_skytrack_list_missions must return UNAVAILABLE with zero orphan IDs."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp import tools

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    (tmp_path / ".token").write_text("PLAINTEXT:valid_token_value_for_test")

    orphan_prj = tmp_path / "prj-01M3ORPHANPRJ000000000000"
    orphan_prj.mkdir(parents=True)
    orphan_mis = orphan_prj / "mis-01M3ORPHANMIS000000000000"
    orphan_mis.mkdir(parents=True)
    (orphan_mis / "mission.json").write_text(json.dumps({"codeMode": False}))

    def failing_catalog(_root):
        raise RuntimeError("Cloud 401 Unauthorized")

    monkeypatch.setattr(tools, "_DEFAULT_CATALOG_PROVIDER", failing_catalog)

    res = tools.tool_skytrack_list_missions()
    assert len(res) == 1
    assert res[0].get("status") == "UNAVAILABLE"
    # Verify zero orphan IDs or paths are emitted in the response
    serialized = json.dumps(res)
    assert "01M3ORPHANMIS000000000000" not in serialized
    assert "01M3ORPHANPRJ000000000000" not in serialized


def test_read_tool_refuses_orphan_local_cache_not_in_authenticated_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Read tools must refuse to load files from local cache dirs not in the authenticated catalog."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp import tools

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)
    (tmp_path / ".token").write_text("PLAINTEXT:valid_token_value_for_test")

    # Stale orphan folder on disk with sensitive payload
    orphan_prj = tmp_path / "prj-01M3ORPHANPRJ000000000000"
    orphan_prj.mkdir(parents=True)
    orphan_mis = orphan_prj / "mis-01M3ORPHANMIS000000000000"
    orphan_mis.mkdir(parents=True)
    (orphan_mis / "mission.json").write_text(
        json.dumps({"codeMode": False, "secret_crop_scan": "CONFIDENTIAL_PAYLOAD_ABC_789"})
    )

    # Active catalog returns only one active mission, excluding the orphan
    def active_catalog(_root):
        return [
            {
                "project_id": "01M3ACTIVEPRJ000000000000",
                "project_name": "Active Farm",
                "mission_id": "01M3ACTIVEMIS000000000000",
                "mission_name": "Active Mission",
            }
        ]

    monkeypatch.setattr(tools, "_DEFAULT_CATALOG_PROVIDER", active_catalog)

    # Attempt to read orphan mission using exact ID
    res_json = tools.tool_skytrack_get_mission_json(
        mission_id="01M3ORPHANMIS000000000000",
        project_id="01M3ORPHANPRJ000000000000",
    )
    assert res_json.get("status") == "PERMISSION_DENIED"
    assert "CONFIDENTIAL_PAYLOAD_ABC_789" not in json.dumps(res_json)

    res_open = tools.tool_skytrack_open_mission(
        mission_id="01M3ORPHANMIS000000000000",
        project_id="01M3ORPHANPRJ000000000000",
    )
    assert res_open.get("status") == "PERMISSION_DENIED"
    assert "CONFIDENTIAL_PAYLOAD_ABC_789" not in json.dumps(res_open)


def test_custom_override_root_without_token_returns_unavailable_zero_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A custom SKYTRACK_CLIENT_DATA directory without an active token must fail closed to UNAVAILABLE."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp import tools

    custom_dir = tmp_path / "custom_data_root"
    stale_prj = custom_dir / "prj-01M3CUSTOMSTALE0000000000"
    stale_mis = stale_prj / "mis-01M3STALEMIS000000000000"
    stale_mis.mkdir(parents=True)
    (stale_mis / "mission.json").write_text(json.dumps({"codeMode": False}))

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", custom_dir)
    monkeypatch.delenv("SKYTRACK_OFFLINE_PROFILE", raising=False)

    res = tools.tool_skytrack_list_missions()
    assert len(res) == 1
    assert res[0].get("status") == "UNAVAILABLE"
    assert "01M3CUSTOMSTALE0000000000" not in json.dumps(res)
    assert "01M3STALEMIS000000000000" not in json.dumps(res)


def test_world_and_vehicle_context_refuse_implicit_inference_from_most_recent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """World and vehicle context queries must reject omitted parameters rather than guessing from missions[0]."""
    from skytrack_mcp.clients import storage_sync
    from skytrack_mcp.mcp import tools

    monkeypatch.setattr(storage_sync, "CLIENT_DATA_DIR", tmp_path)

    p1 = tmp_path / "prj-01M3PRJ10000000000000000"
    m1 = p1 / "mis-01M3MIS10000000000000000"
    m1.mkdir(parents=True)
    (m1 / "mission.json").write_text(json.dumps({"world": "warehouse", "vehicle": "x500_livox_mid_360"}))

    p2 = tmp_path / "prj-01M3PRJ20000000000000000"
    m2 = p2 / "mis-01M3MIS20000000000000000"
    m2.mkdir(parents=True)
    (m2 / "mission.json").write_text(json.dumps({"world": "farm-petersburg", "vehicle": "x500_spray"}))

    # Reject omitted world_name
    with pytest.raises(ValueError, match="Explicit world_name or exact"):
        tools.tool_skytrack_get_world_context(world_name=None)

    # Reject omitted vehicle_model
    with pytest.raises(ValueError, match="Explicit vehicle_model or exact"):
        tools.tool_skytrack_get_vehicle_context(vehicle_model=None)

    # Explicit world_name succeeds with truthful packaged reference labels
    w_info = tools.tool_skytrack_get_world_context(world_name="warehouse")
    assert w_info["world"] == "warehouse"
    assert w_info["source"] == "packaged_sdf_reference"
    assert w_info["active_simulation_provenance"] == "UNKNOWN"

    # Explicit vehicle_model succeeds
    v_info = tools.tool_skytrack_get_vehicle_context(vehicle_model="x500_spray")
    assert v_info["vehicle"] == "x500_spray"


def test_tool_skytrack_list_worlds_labels_packaged_sdf_reference():
    """tool_skytrack_list_worlds advertises offline packaged SDF reference, not active simulation world."""
    from skytrack_mcp.mcp.tools import tool_skytrack_list_worlds

    res = tool_skytrack_list_worlds()
    assert res["source"] == "packaged_sdf_reference"
    assert res["active_simulation_world"] == "UNKNOWN"
    assert "warehouse" in res["packaged_worlds"]
