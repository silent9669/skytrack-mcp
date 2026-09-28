"""Exact Project and Mission Target Resolution for SkyTrack MCP.

Enforces:
1. Exact name/ID resolution without guessing
2. Detection of ambiguous duplicate names with structured candidate list
3. Prohibition of silent fallback to most-recently-modified mission
4. Prohibition of arbitrary project creation without explicit confirmation
5. Authoritative Cloud catalog as primary source of truth, checking local cache presence,
   failing closed to UNAVAILABLE when catalog is unreachable or unverified, and strictly
   redacting sensitive mission commands and payloads from error logs.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from skytrack_mcp.clients.cloud_client import call_cloud_api
from skytrack_mcp.config import CLIENT_DATA_DIR


class TargetResolutionStatus(str, Enum):
    EXACT = "EXACT"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class TargetResolutionResult:
    status: TargetResolutionStatus
    project_id: str | None = None
    project_name: str | None = None
    mission_id: str | None = None
    mission_name: str | None = None
    path: str | None = None
    cached_locally: bool = True
    candidates: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "mission_id": self.mission_id,
            "mission_name": self.mission_name,
            "path": self.path,
            "cached_locally": self.cached_locally,
            "candidates": self.candidates,
            "error_message": self.error_message,
        }


def _normalize_id(raw_id: str, prefix: str) -> str:
    """Strip prefix if present."""
    return raw_id.removeprefix(prefix).strip()


def _looks_like_stable_id(val: str, prefix: str) -> bool:
    """Return True if val starts with the ID prefix or is a 26-char uppercase ULID."""
    raw = val.strip()
    if raw.startswith(prefix):
        return True
    return len(raw) == 26 and raw.isalnum() and raw.isupper()


def _extract_list_payload(resp: Any, key: str) -> list[dict[str, Any]]:
    """Extract list of dicts from SkyTrack BFF response envelope ({data: ...} or direct list).

    Strictly validates that all items are dictionaries; never leaks raw responses in errors.
    """
    raw_list: list[Any] | None = None
    if isinstance(resp, list):
        raw_list = resp
    elif isinstance(resp, dict):
        data = resp.get("data")
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            nested = data.get(key)
            if isinstance(nested, list):
                raw_list = nested
        if raw_list is None:
            direct = resp.get(key)
            if isinstance(direct, list):
                raw_list = direct

    if raw_list is None:
        raise ValueError(f"Unexpected SkyTrack catalog response envelope for '{key}': type={type(resp).__name__}")

    for idx, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise TypeError(
                f"Malformed catalog payload in '{key}': item at index {idx} is type={type(item).__name__}, expected dict"
            )

    return raw_list


def fetch_cloud_mission_catalog(
    client_data_dir: Path | None = None,
    api_caller: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch complete project and mission name catalog from SkyTrack Cloud session.

    Queries `/api/v1/projects` and per-project `/api/v1/projects/{id}` details, verifying
    `totalMissions` exact completeness and raising loudly on any partial, stalled, or malformed
    response without leaking sensitive mission commands/payloads in error messages.
    """
    root = client_data_dir or CLIENT_DATA_DIR
    if sys.platform.startswith("linux") and api_caller is None:
        raise RuntimeError("Linux desktop session decryption is unverified; catalog unavailable.")

    caller = api_caller or call_cloud_api
    project_records: list[dict[str, Any]] = []
    project_names: dict[str, str] = {}

    # 1. Paginate through all projects with no-progress loop safety
    page_size = 20
    offset = 0
    seen_proj_ids: set[str] = set()

    while True:
        params: dict[str, Any] = {
            "offset": offset,
            "limit": page_size,
            "sort_field": "updated_at",
            "sort_direction": "desc",
        }

        proj_resp = caller("/api/v1/projects", method="GET", params=params, client_data_dir=root)
        proj_batch = _extract_list_payload(proj_resp, "projects")
        if not proj_batch:
            break

        new_proj_ids: set[str] = set()
        for idx, p in enumerate(proj_batch):
            pid = _normalize_id(str(p.get("id") or ""), "prj-")
            pname = str(p.get("name") or "").strip()
            if not pid or not pname:
                raise ValueError(f"Malformed project item at index {idx} in catalog: missing id or name")
            project_names[pid] = pname
            project_records.append(p)
            new_proj_ids.add(pid)

        # Detect stalled pagination / duplicate page
        if not (new_proj_ids - seen_proj_ids):
            raise ValueError(
                f"Catalog pagination stalled: received duplicate project page at offset {offset} with no new records"
            )
        seen_proj_ids.update(new_proj_ids)
        offset += len(proj_batch)

    entries: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # 2. Fetch per-project detail (/api/v1/projects/{id}) and verify exact totalMissions cardinality
    for p in project_records:
        pid = _normalize_id(str(p.get("id") or ""), "prj-")
        pname = str(p.get("name") or "").strip()
        expected_total = p.get("totalMissions")

        detail_resp = caller(f"/api/v1/projects/{pid}", method="GET", client_data_dir=root)
        mis_batch = _extract_list_payload(detail_resp, "missions")

        if expected_total is not None and len(mis_batch) != int(expected_total):
            raise ValueError(
                f"Incomplete or mismatched missions count in project '{pid}': expected {expected_total}, got {len(mis_batch)}"
            )

        for idx, m in enumerate(mis_batch):
            mid = _normalize_id(str(m.get("id") or ""), "mis-")
            mname = str(m.get("name") or "").strip()
            if not mid or not mname:
                raise ValueError(f"Malformed mission item at index {idx} in project '{pid}': missing id or name")

            claimed_prj = m.get("projectId")
            if claimed_prj and _normalize_id(str(claimed_prj), "prj-") != pid:
                raise ValueError(
                    f"Mission linkage mismatch: mission at index {idx} in project '{pid}' claims projectId '{claimed_prj}'"
                )

            if (pid, mid) in seen_pairs:
                raise ValueError(f"Duplicate mission item at index {idx} in project '{pid}' catalog")

            entries.append(
                {
                    "project_id": pid,
                    "project_name": pname,
                    "mission_id": mid,
                    "mission_name": mname,
                }
            )
            seen_pairs.add((pid, mid))

    return entries


def list_project_and_mission_catalog(
    client_data_dir: Path | None = None,
    catalog_provider: Callable[[Path], list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Build unified catalog of projects and missions, checking local cache presence.

    When an authoritative catalog_provider succeeds, the active user's catalog contains
    ONLY their authenticated missions (with cached_locally: bool and path: str | None).
    Unverified local disk folders from other accounts are strictly isolated and not appended.
    Local disk entries are used only when the catalog provider is unavailable/offline.
    """
    root = client_data_dir or CLIENT_DATA_DIR
    catalog: list[dict[str, Any]] = []
    if not root.exists():
        return catalog, True

    catalog_failed = False
    authoritative_entries: list[dict[str, Any]] = []

    if catalog_provider is not None:
        try:
            raw_entries = catalog_provider(root)
            if not isinstance(raw_entries, list):
                catalog_failed = True
            else:
                authoritative_entries = raw_entries
        except (RuntimeError, ValueError, TypeError, OSError, urllib.error.URLError, ConnectionError):
            catalog_failed = True

    seen_pairs: set[tuple[str, str]] = set()

    # Case A: Authoritative catalog provider was supplied
    if catalog_provider is not None:
        if catalog_failed:
            # Do NOT fall back to local disk directories on auth/network failure;
            # return empty catalog so zero unverified/other-account IDs or paths are leaked.
            return [], True

        for entry in authoritative_entries:
            if not isinstance(entry, dict):
                continue
            pid = _normalize_id(str(entry.get("project_id") or ""), "prj-")
            mid = _normalize_id(str(entry.get("mission_id") or ""), "mis-")
            pname = entry.get("project_name")
            mname = entry.get("mission_name")
            if not pid or not mid:
                continue

            mis_dir = root / f"prj-{pid}" / f"mis-{mid}"
            cached = mis_dir.is_dir() and (mis_dir / "mission.json").exists()

            catalog.append(
                {
                    "project_id": pid,
                    "project_name": str(pname).strip() if pname else None,
                    "mission_id": mid,
                    "mission_name": str(mname).strip() if mname else None,
                    "path": str(mis_dir) if cached else None,
                    "cached_locally": cached,
                }
            )
            seen_pairs.add((pid, mid))
        return catalog, False

    # Case B: Explicit offline/local-only mode (only when catalog_provider is None)
    for prj_dir in root.glob("prj-*"):
        if not prj_dir.is_dir():
            continue
        project_id = prj_dir.name.removeprefix("prj-")
        project_name: str | None = None
        prj_meta_file = prj_dir / "project.json"
        if prj_meta_file.exists():
            try:
                prj_meta = json.loads(prj_meta_file.read_text(encoding="utf-8"))
                project_name = prj_meta.get("name")
            except (json.JSONDecodeError, OSError):
                pass

        for mis_dir in prj_dir.glob("mis-*"):
            if not mis_dir.is_dir():
                continue
            mission_id = mis_dir.name.removeprefix("mis-")
            if (project_id, mission_id) in seen_pairs:
                continue

            mission_name: str | None = None
            mis_meta_file = mis_dir / "mission.json"
            if mis_meta_file.exists():
                try:
                    mis_meta = json.loads(mis_meta_file.read_text(encoding="utf-8"))
                    mission_name = mis_meta.get("name")
                except (json.JSONDecodeError, OSError):
                    pass

            catalog.append(
                {
                    "project_id": project_id,
                    "project_name": project_name,
                    "mission_id": mission_id,
                    "mission_name": mission_name,
                    "path": str(mis_dir),
                    "cached_locally": True,
                    "local_only": True,
                }
            )

    return catalog, catalog_failed


def resolve_exact_target(
    client_data_dir: Path | None = None,
    project_name_or_id: str | None = None,
    mission_name_or_id: str | None = None,
    allow_create: bool = False,
    catalog_provider: Callable[[Path], list[dict[str, Any]]] | None = None,
) -> TargetResolutionResult:
    """Resolve project and mission to an exact, unambiguous pair.

    - If mission_name_or_id is omitted: returns MISSING (never falls back to missions[0]).
    - If multiple matches exist: returns AMBIGUOUS with candidates.
    - If user specifies a human-readable name when catalog provider failed: returns UNAVAILABLE
      BEFORE evaluating local cache files to prevent resolving against stale/tampered names.
    - If catalog is complete and no match exists: returns MISSING.
    - If mission exists in authoritative account but is not cached locally: returns EXACT
      with cached_locally=False and path=None (never falsely reports MISSING).
    """
    root = client_data_dir or CLIENT_DATA_DIR
    if not root.exists():
        return TargetResolutionResult(
            status=TargetResolutionStatus.UNAVAILABLE,
            error_message=f"ClientData directory does not exist: {root}",
        )

    all_catalog, catalog_failed = list_project_and_mission_catalog(root, catalog_provider=catalog_provider)

    # CRITICAL: When an authoritative catalog provider is configured and fails,
    # fail closed to UNAVAILABLE with empty candidates for ALL queries (both names and IDs)
    # so zero unverified local cache folders or other-account IDs are exposed.
    if catalog_provider is not None and catalog_failed:
        return TargetResolutionResult(
            status=TargetResolutionStatus.UNAVAILABLE,
            candidates=[],
            error_message=(
                "Authoritative SkyTrack catalog provider failed or is unavailable. "
                "Access to local cache directories is blocked when account ownership cannot be verified."
            ),
        )

    if not mission_name_or_id or not mission_name_or_id.strip():
        return TargetResolutionResult(
            status=TargetResolutionStatus.MISSING,
            candidates=all_catalog,
            error_message="No mission specified. You must provide an exact mission name or ID.",
        )

    clean_mission = mission_name_or_id.strip()
    clean_mission_id = _normalize_id(clean_mission, "mis-")
    clean_project = project_name_or_id.strip() if project_name_or_id else None
    clean_project_id = _normalize_id(clean_project, "prj-") if clean_project else None

    # Filter by project if specified
    project_catalog = all_catalog
    if clean_project and clean_project_id:
        # Match project by ID or exact name (case-insensitive)
        matched_projects = [
            item
            for item in all_catalog
            if item["project_id"] == clean_project_id
            or (item["project_name"] and item["project_name"].lower() == clean_project.lower())
        ]

        if not matched_projects:
            has_any_project_names = any(bool(item.get("project_name")) for item in all_catalog)
            if (catalog_failed or not has_any_project_names) and not _looks_like_stable_id(clean_project, "prj-"):
                return TargetResolutionResult(
                    status=TargetResolutionStatus.UNAVAILABLE,
                    candidates=all_catalog,
                    error_message=(
                        f"Human-readable project catalog is unavailable from SkyTrack. "
                        f"Cannot resolve project name '{clean_project}'. Please provide the exact project ID."
                    ),
                )

            return TargetResolutionResult(
                status=TargetResolutionStatus.MISSING,
                error_message=f"Project '{project_name_or_id}' not found in ClientData.",
                candidates=all_catalog,
            )

        unique_project_ids = {p["project_id"] for p in matched_projects}
        if len(unique_project_ids) > 1:
            return TargetResolutionResult(
                status=TargetResolutionStatus.AMBIGUOUS,
                candidates=matched_projects,
                error_message=(
                    f"Multiple projects share the name '{clean_project}'. "
                    f"Please disambiguate by specifying an exact project ID: {sorted(unique_project_ids)}"
                ),
            )

        project_catalog = matched_projects

    # Find mission matches in the filtered catalog
    # Priority 1: Exact ID match
    id_matches = [
        item for item in project_catalog if item["mission_id"] == clean_mission_id
    ]
    if id_matches:
        if len(id_matches) == 1:
            match = id_matches[0]
            err_msg = (
                None
                if match.get("cached_locally", True)
                else "Mission exists in SkyTrack Cloud account but artifact is not yet cached locally. Open the mission in SkyTrack Desktop to download."
            )
            return TargetResolutionResult(
                status=TargetResolutionStatus.EXACT,
                project_id=match["project_id"],
                project_name=match["project_name"],
                mission_id=match["mission_id"],
                mission_name=match["mission_name"],
                path=match["path"],
                cached_locally=match.get("cached_locally", True),
                error_message=err_msg,
            )
        return TargetResolutionResult(
            status=TargetResolutionStatus.AMBIGUOUS,
            candidates=id_matches,
            error_message=f"Duplicate mission ID across multiple projects: {clean_mission_id}",
        )

    # Priority 2: Exact Name match (case-insensitive)
    name_matches = [
        item
        for item in project_catalog
        if item["mission_name"] and item["mission_name"].lower() == clean_mission.lower()
    ]
    if len(name_matches) == 1:
        match = name_matches[0]
        err_msg = (
            None
            if match.get("cached_locally", True)
            else "Mission exists in SkyTrack Cloud account but artifact is not yet cached locally. Open the mission in SkyTrack Desktop to download."
        )
        return TargetResolutionResult(
            status=TargetResolutionStatus.EXACT,
            project_id=match["project_id"],
            project_name=match["project_name"],
            mission_id=match["mission_id"],
            mission_name=match["mission_name"],
            path=match["path"],
            cached_locally=match.get("cached_locally", True),
            error_message=err_msg,
        )
    elif len(name_matches) > 1:
        return TargetResolutionResult(
            status=TargetResolutionStatus.AMBIGUOUS,
            candidates=name_matches,
            error_message=(
                f"Multiple missions match the name '{clean_mission}'. "
                "Please disambiguate by specifying project ID and mission ID."
            ),
        )

    # If no name match, check whether human names were unavailable or catalog failed
    has_any_mission_names = any(bool(item.get("mission_name")) for item in project_catalog)
    if (catalog_failed or not has_any_mission_names) and not _looks_like_stable_id(clean_mission, "mis-"):
        return TargetResolutionResult(
            status=TargetResolutionStatus.UNAVAILABLE,
            candidates=project_catalog,
            error_message=(
                f"Human-readable mission catalog is unavailable from SkyTrack. "
                f"Cannot resolve mission name '{clean_mission}'. Please provide the exact mission ID."
            ),
        )

    # No match found in complete catalog
    available_names = [c["mission_name"] or c["mission_id"] for c in project_catalog]
    return TargetResolutionResult(
        status=TargetResolutionStatus.MISSING,
        candidates=project_catalog,
        error_message=(
            f"Mission '{clean_mission}' not found. "
            f"Available missions in scope: {available_names}"
        ),
    )
