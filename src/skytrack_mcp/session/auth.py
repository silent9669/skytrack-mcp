"""SkyTrack App session identity, edit authorization gating, and build compatibility.

Enforces:
1. Filesystem writability alone NEVER grants edit authorization.
2. Local unverified project.json alone NEVER grants VERIFIED status (untrusted cache).
3. Authoritative verification via verified SkyTrack Cloud API (GET /api/v1/projects) or
   an injected authoritative validator is required to grant VERIFIED.
4. If permission is unverified or view-only, returns PERMISSION_UNVERIFIED and enforces read-only.
5. Redacts all sensitive token contents from return structures and logs.
6. Fails closed (APP_COMPATIBILITY_UNKNOWN) on conflicting App bundle/process versions
   or unverified build profiles.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from skytrack_mcp.clients.cloud_client import (
    call_cloud_api,
    decrypt_client_data_file,
    list_cloud_projects,
)
from skytrack_mcp.config import CLIENT_DATA_DIR

# Pinned build profile for the verified 1.2.7 Electron bundle
VERIFIED_1_2_7_ASAR_SHA256 = "c49435c46a41dfdbf330fca29ac3c7740eb79d879069fb4defd6d37682915601"
DEFAULT_MACOS_ASAR_PATH = Path("/Applications/SkyTrack.app/Contents/Resources/app.asar")


class EditAuthorizationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"
    UNVERIFIED = "UNVERIFIED"


class AppCompatibilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class PermissionCheckResult:
    edit_authorization: EditAuthorizationStatus
    project_id: str
    mission_id: str | None = None
    role: str | None = None
    read_only_enforced: bool = True
    reason: str = ""
    app_compatibility: AppCompatibilityStatus = AppCompatibilityStatus.UNKNOWN
    bundle_version: str | None = None
    process_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize without exposing any authentication secrets."""
        return {
            "edit_authorization": self.edit_authorization.value,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "role": self.role,
            "read_only_enforced": self.read_only_enforced,
            "reason": self.reason,
            "app_compatibility": self.app_compatibility.value,
            "bundle_version": self.bundle_version,
            "process_version": self.process_version,
        }


def detect_installed_app_version() -> str | None:
    """Detect version of installed SkyTrack Desktop application."""
    if sys.platform == "darwin":
        plist_path = Path("/Applications/SkyTrack.app/Contents/Info.plist")
        if plist_path.exists():
            try:
                txt = plist_path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", txt)
                if match:
                    return match.group(1).strip()
            except (OSError, UnicodeDecodeError):
                pass
    elif sys.platform.startswith("linux"):
        pkg_json = Path("/opt/SkyTrack/resources/app/package.json")
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                return data.get("version")
            except (json.JSONDecodeError, OSError):
                pass
    return None


def calculate_installed_asar_hash(asar_path: Path | None = None) -> str | None:
    """Calculate SHA-256 of installed app.asar bundle."""
    target = asar_path or DEFAULT_MACOS_ASAR_PATH
    if not target.exists():
        return None
    try:
        h = hashlib.sha256()
        with open(target, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().lower()
    except OSError:
        return None


def is_verified_1_2_7_build(asar_path: Path | None = None) -> bool:
    """Check if installed Desktop app matches the exact verified 1.2.7 build profile."""
    version = detect_installed_app_version()
    if version != "1.2.7":
        return False
    if sys.platform == "darwin":
        current_hash = calculate_installed_asar_hash(asar_path=asar_path)
        return current_hash == VERIFIED_1_2_7_ASAR_SHA256
    return False


def query_authoritative_project_role(
    project_id: str,
    client_data_dir: Path | None = None,
) -> dict[str, Any]:
    """Query SkyTrack Cloud BFF (/api/v1/user/me and /api/v1/projects) for authoritative role."""
    root = client_data_dir or CLIENT_DATA_DIR
    clean_prj = project_id.removeprefix("prj-").strip()
    if not clean_prj:
        return {}

    user_id = ""
    try:
        me_resp = call_cloud_api("/api/v1/user/me", method="GET", client_data_dir=root)
        if isinstance(me_resp, dict):
            data_obj = me_resp.get("data") if isinstance(me_resp.get("data"), dict) else me_resp
            user_id = str(data_obj.get("id") or "").strip()
    except (RuntimeError, ValueError, TypeError, OSError):
        user_id = ""

    try:
        projects_resp = list_cloud_projects(client_data_dir=root)
        items = (
            projects_resp.get("data", [])
            if isinstance(projects_resp, dict)
            else (projects_resp if isinstance(projects_resp, list) else [])
        )
        for p in items:
            if not isinstance(p, dict):
                continue
            p_id = str(p.get("id") or "").removeprefix("prj-").strip()
            if p_id != clean_prj:
                continue

            if p.get("sharedViewOnly") or p.get("view_only") or p.get("immutable"):
                return {"role": "viewer"}

            explicit_role = p.get("role") or p.get("permission")
            if explicit_role:
                return {"role": str(explicit_role).lower()}

            owner_id = str(p.get("ownerId") or p.get("owner_id") or "").strip()
            if user_id and owner_id:
                if owner_id == user_id:
                    return {"role": "owner"}
                return {"role": "viewer"}
    except (RuntimeError, ValueError, TypeError, OSError):
        return {}

    return {}


def verify_project_edit_permission(
    client_data_dir: Path | None = None,
    project_id: str = "",
    mission_id: str | None = None,
    authoritative_checker: Callable[[str, Path], dict[str, Any]] | None = None,
) -> PermissionCheckResult:
    """Verify whether the current SkyTrack session has verified edit rights to the project/mission.

    Local filesystem writability or local unverified project.json alone does NOT confer edit rights.
    Requires authoritative verification against active session or injected authoritative checker.
    """
    root = client_data_dir or CLIENT_DATA_DIR
    clean_prj = project_id.removeprefix("prj-").strip()
    clean_mis = mission_id.removeprefix("mis-").strip() if mission_id else None

    # 1. Verify active decrypted session exists in ClientData
    if sys.platform.startswith("linux") and authoritative_checker is None:
        return PermissionCheckResult(
            edit_authorization=EditAuthorizationStatus.UNVERIFIED,
            project_id=clean_prj,
            mission_id=clean_mis,
            read_only_enforced=True,
            reason="PERMISSION_UNVERIFIED: Linux desktop session decryption is unverified; read-only mode enforced.",
        )

    try:
        token_str = decrypt_client_data_file(root / ".token")
        csrf_str = decrypt_client_data_file(root / ".csrf")
    except (ValueError, TypeError, OSError, RuntimeError):
        token_str = ""
        csrf_str = ""

    has_active_session = bool(token_str and csrf_str and len(token_str) > 10)

    if not has_active_session:
        return PermissionCheckResult(
            edit_authorization=EditAuthorizationStatus.UNVERIFIED,
            project_id=clean_prj,
            mission_id=clean_mis,
            read_only_enforced=True,
            reason="PERMISSION_UNVERIFIED: No active decrypted SkyTrack Desktop session found in ClientData.",
        )

    # 2. Check local mission metadata for existence and lock/immutable states
    prj_dir = root / f"prj-{clean_prj}"
    if clean_mis:
        mis_dir = prj_dir / f"mis-{clean_mis}"
        mis_meta_file = mis_dir / "mission.json"
        if not mis_meta_file.exists():
            return PermissionCheckResult(
                edit_authorization=EditAuthorizationStatus.UNVERIFIED,
                project_id=clean_prj,
                mission_id=clean_mis,
                read_only_enforced=True,
                reason=(
                    f"PERMISSION_UNVERIFIED: Target mission '{clean_mis}' does not exist in project '{clean_prj}'. "
                    "Operator confirmation is required before creating a missing mission."
                ),
            )
        try:
            mis_meta = json.loads(mis_meta_file.read_text(encoding="utf-8"))
            if mis_meta.get("immutable") or mis_meta.get("locked") or mis_meta.get("sharedViewOnly"):
                return PermissionCheckResult(
                    edit_authorization=EditAuthorizationStatus.DENIED,
                    project_id=clean_prj,
                    mission_id=clean_mis,
                    read_only_enforced=True,
                    reason="Edit permission denied: mission is an immutable or locked judge/submission snapshot.",
                )
        except (json.JSONDecodeError, OSError):
            pass

    # Check local project.json for explicit view-only flag
    prj_meta_file = prj_dir / "project.json"
    if prj_meta_file.exists():
        try:
            local_meta = json.loads(prj_meta_file.read_text(encoding="utf-8"))
            if local_meta.get("view_only") or local_meta.get("immutable") or local_meta.get("role") == "viewer":
                return PermissionCheckResult(
                    edit_authorization=EditAuthorizationStatus.DENIED,
                    project_id=clean_prj,
                    mission_id=clean_mis,
                    role="viewer",
                    read_only_enforced=True,
                    reason="Edit permission denied: project is marked view-only or user has viewer role.",
                )
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Authoritative verification of project edit role
    authoritative_role: str | None = None
    if authoritative_checker is not None:
        try:
            auth_info = authoritative_checker(clean_prj, root)
            authoritative_role = auth_info.get("role") or auth_info.get("permission")
        except (RuntimeError, ValueError, OSError, ConnectionError):
            authoritative_role = None
    else:
        try:
            auth_info = query_authoritative_project_role(clean_prj, root)
            authoritative_role = auth_info.get("role") or auth_info.get("permission")
        except (RuntimeError, ValueError, OSError, ConnectionError):
            authoritative_role = None

    if authoritative_role in ("owner", "editor", "admin", "write"):
        return PermissionCheckResult(
            edit_authorization=EditAuthorizationStatus.VERIFIED,
            project_id=clean_prj,
            mission_id=clean_mis,
            role=authoritative_role,
            read_only_enforced=False,
            reason="Verified edit permission from authoritative SkyTrack session and project role.",
        )

    if authoritative_role in ("viewer", "read", "view_only"):
        return PermissionCheckResult(
            edit_authorization=EditAuthorizationStatus.DENIED,
            project_id=clean_prj,
            mission_id=clean_mis,
            role=authoritative_role,
            read_only_enforced=True,
            reason="Edit permission denied: authoritative SkyTrack role is viewer.",
        )

    # If authoritative check could not confirm edit rights, fail closed to read-only UNVERIFIED
    return PermissionCheckResult(
        edit_authorization=EditAuthorizationStatus.UNVERIFIED,
        project_id=clean_prj,
        mission_id=clean_mis,
        read_only_enforced=True,
        reason=(
            "PERMISSION_UNVERIFIED: Local filesystem is writable, but authoritative SkyTrack "
            "project edit authorization could not be verified against the session."
        ),
    )


def probe_app_build_compatibility(
    bundle_version: str | None = None,
    process_version: str | None = None,
    asar_path: Path | None = None,
) -> dict[str, Any]:
    """Verify build compatibility between installed bundle and running process.

    Fails closed to UNKNOWN unless exact build profile (1.2.7 and matching asar hash)
    is validated with empirical evidence.
    """
    bundle_v = bundle_version or detect_installed_app_version()
    process_v = process_version

    if not bundle_v or not process_v:
        return {
            "status": AppCompatibilityStatus.UNKNOWN.value,
            "bundle_version": bundle_v,
            "process_version": process_v,
            "reason": "App build version could not be independently verified across bundle and process.",
        }

    if bundle_v != process_v:
        return {
            "status": AppCompatibilityStatus.UNKNOWN.value,
            "bundle_version": bundle_v,
            "process_version": process_v,
            "reason": (
                f"App build version mismatch: bundle reports {bundle_v} while "
                f"running process reports {process_v}."
            ),
        }

    if bundle_v == "1.2.7" and is_verified_1_2_7_build(asar_path=asar_path):
        return {
            "status": AppCompatibilityStatus.SUPPORTED.value,
            "bundle_version": bundle_v,
            "process_version": process_v,
            "reason": f"App build verified compatible with pinned 1.2.7 profile (hash {VERIFIED_1_2_7_ASAR_SHA256[:12]}...).",
        }

    return {
        "status": AppCompatibilityStatus.UNKNOWN.value,
        "bundle_version": bundle_v,
        "process_version": process_v,
        "reason": f"App build version {bundle_v} is unverified or lacks empirical adapter profile.",
    }
