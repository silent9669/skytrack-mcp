"""Unit tests for SkyTrack App session, authoritative edit authorization, and build compatibility."""

from __future__ import annotations

import json
from pathlib import Path

from skytrack_mcp.session.auth import (
    AppCompatibilityStatus,
    EditAuthorizationStatus,
    probe_app_build_compatibility,
    verify_project_edit_permission,
)


def test_writable_filesystem_alone_is_unverified(tmp_path: Path):
    """A writable local directory with mission.json but no verified session/role must return UNVERIFIED."""
    prj_dir = tmp_path / "prj-01M3TESTPRJ000000000000000"
    mis_dir = prj_dir / "mis-01M3TESTMIS000000000000000"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(json.dumps({"name": "Test Mission", "codeMode": False}))

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3TESTPRJ000000000000000",
        mission_id="01M3TESTMIS000000000000000",
    )
    assert res.edit_authorization == EditAuthorizationStatus.UNVERIFIED
    assert res.read_only_enforced is True
    assert "PERMISSION_UNVERIFIED" in res.reason


def test_malformed_encrypted_token_returns_unverified(tmp_path: Path):
    """Malformed ENCRYPTED token payload must fail closed to UNVERIFIED without raising ValueError."""
    (tmp_path / ".token").write_text("ENCRYPTED:not-hex:zz")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3TESTPRJ000000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "owner"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.UNVERIFIED
    assert res.read_only_enforced is True
    assert "not-hex:zz" not in json.dumps(res.to_dict())


def test_empty_ciphertext_token_returns_unverified(tmp_path: Path):
    """Encrypted token with valid IV but empty ciphertext must fail closed to UNVERIFIED without IndexError."""
    (tmp_path / ".token").write_text("ENCRYPTED:" + "00" * 16 + ":")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3TESTPRJ000000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "owner"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.UNVERIFIED
    assert res.read_only_enforced is True


def test_session_with_local_owner_file_without_authoritative_check_is_unverified(tmp_path: Path):
    """Local project.json claiming role=owner alone is untrusted cache and must return UNVERIFIED."""
    (tmp_path / ".token").write_text("PLAINTEXT:secret_jwt_token_value_long_enough")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    prj_dir = tmp_path / "prj-01M3TESTPRJ000000000000000"
    prj_dir.mkdir(parents=True)
    (prj_dir / "project.json").write_text(
        json.dumps({"id": "01M3TESTPRJ000000000000000", "name": "Forged Owner Project", "role": "owner"})
    )

    # Injected authoritative check fails or is unreachable
    def unreachable_auth(_prj, _root):
        raise ConnectionError("Cloud API unreachable")

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3TESTPRJ000000000000000",
        authoritative_checker=unreachable_auth,
    )
    assert res.edit_authorization == EditAuthorizationStatus.UNVERIFIED
    assert res.read_only_enforced is True
    # Ensure secrets never leak into output dict
    serialized = json.dumps(res.to_dict())
    assert "secret_jwt_token_value" not in serialized
    assert "secret_csrf_token_value" not in serialized


def test_authoritative_viewer_role_is_denied(tmp_path: Path):
    """If authoritative session reports viewer role, return DENIED."""
    (tmp_path / ".token").write_text("PLAINTEXT:secret_jwt_token_value_long_enough")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    prj_dir = tmp_path / "prj-01M3VIEWONLY00000000000000"
    prj_dir.mkdir(parents=True)

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3VIEWONLY00000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "viewer"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.DENIED
    assert res.read_only_enforced is True


def test_authoritative_owner_role_with_active_session_is_verified(tmp_path: Path):
    """When session is active and authoritative check returns owner/editor, return VERIFIED."""
    (tmp_path / ".token").write_text("PLAINTEXT:secret_jwt_token_value_long_enough")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    prj_dir = tmp_path / "prj-01M3OWNERPRJ00000000000000"
    mis_dir = prj_dir / "mis-01M3OWNERMIS00000000000000"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(
        json.dumps({"name": "Editable Mission", "codeMode": False})
    )

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3OWNERPRJ00000000000000",
        mission_id="01M3OWNERMIS00000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "owner"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.VERIFIED
    assert res.read_only_enforced is False
    assert res.role == "owner"


def test_missing_targeted_mission_is_unverified_even_for_owner(tmp_path: Path):
    """When project owner role is authoritative, but the targeted mission does not exist, return UNVERIFIED."""
    (tmp_path / ".token").write_text("PLAINTEXT:secret_jwt_token_value_long_enough")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    prj_dir = tmp_path / "prj-01M3OWNERPRJ00000000000000"
    prj_dir.mkdir(parents=True)

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3OWNERPRJ00000000000000",
        mission_id="01M3NONEXISTENT000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "owner"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.UNVERIFIED
    assert res.read_only_enforced is True
    assert "does not exist" in res.reason.lower()


def test_locked_judge_snapshot_mission_is_denied_even_for_owner(tmp_path: Path):
    """An immutable judge/submission mission snapshot must be DENIED even if authoritative role is owner."""
    (tmp_path / ".token").write_text("PLAINTEXT:secret_jwt_token_value_long_enough")
    (tmp_path / ".csrf").write_text("PLAINTEXT:secret_csrf_token_value_long_enough")

    prj_dir = tmp_path / "prj-01M3OWNERPRJ00000000000000"
    mis_dir = prj_dir / "mis-01M3LOCKEDMS00000000000000"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(
        json.dumps({"name": "Submitted Mission", "immutable": True})
    )

    res = verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3OWNERPRJ00000000000000",
        mission_id="01M3LOCKEDMS00000000000000",
        authoritative_checker=lambda _prj, _root: {"role": "owner"},
    )
    assert res.edit_authorization == EditAuthorizationStatus.DENIED
    assert res.read_only_enforced is True


def test_app_build_compatibility_fails_closed_to_unknown():
    """Verify build compatibility fails closed to UNKNOWN when not empirically validated."""
    # Mismatch fails closed
    compat_mismatch = probe_app_build_compatibility(bundle_version="1.2.5", process_version="1.2.6")
    assert compat_mismatch["status"] == AppCompatibilityStatus.UNKNOWN.value
    assert "mismatch" in compat_mismatch["reason"].lower()

    # Missing process version fails closed
    compat_missing = probe_app_build_compatibility(bundle_version="1.2.6", process_version=None)
    assert compat_missing["status"] == AppCompatibilityStatus.UNKNOWN.value

    # Matching versions without empirical profile validation remain UNKNOWN
    compat_unvalidated = probe_app_build_compatibility(bundle_version="1.2.6", process_version="1.2.6")
    assert compat_unvalidated["status"] == AppCompatibilityStatus.UNKNOWN.value
    assert "unverified" in compat_unvalidated["reason"].lower()


def test_query_authoritative_project_role_owner(tmp_path: Path, monkeypatch):
    """When /api/v1/user/me id matches project ownerId, authoritative role is owner."""
    from skytrack_mcp.session import auth

    monkeypatch.setattr(
        auth,
        "call_cloud_api",
        lambda endpoint, method="GET", client_data_dir=None: {"id": "usr-12345", "email": "pilot@example.com"},
    )
    monkeypatch.setattr(
        auth,
        "list_cloud_projects",
        lambda client_data_dir=None: [{"id": "01M3PRJTEST", "ownerId": "usr-12345", "name": "My Farm"}],
    )

    role_info = auth.query_authoritative_project_role("01M3PRJTEST", client_data_dir=tmp_path)
    assert role_info == {"role": "owner"}


def test_query_authoritative_project_role_shared_view_only(tmp_path: Path, monkeypatch):
    """When project is shared view only, authoritative role is viewer."""
    from skytrack_mcp.session import auth

    monkeypatch.setattr(
        auth,
        "call_cloud_api",
        lambda endpoint, method="GET", client_data_dir=None: {"id": "usr-12345"},
    )
    monkeypatch.setattr(
        auth,
        "list_cloud_projects",
        lambda client_data_dir=None: [{"id": "01M3PRJTEST", "ownerId": "usr-12345", "sharedViewOnly": True}],
    )

    role_info = auth.query_authoritative_project_role("01M3PRJTEST", client_data_dir=tmp_path)
    assert role_info == {"role": "viewer"}


def test_verify_project_edit_permission_default_authoritative_cloud_lookup(tmp_path: Path, monkeypatch):
    """verify_project_edit_permission without authoritative_checker resolves via Cloud API."""
    from skytrack_mcp.session import auth

    (tmp_path / ".token").write_text("PLAINTEXT:valid_active_jwt_token_1234567890")
    (tmp_path / ".csrf").write_text("PLAINTEXT:valid_active_csrf_token_1234567890")

    prj_dir = tmp_path / "prj-01M3CLOUDPRJ"
    mis_dir = prj_dir / "mis-01M3CLOUDMIS"
    mis_dir.mkdir(parents=True)
    (mis_dir / "mission.json").write_text(json.dumps({"name": "Cloud Mission", "codeMode": False}))

    monkeypatch.setattr(
        auth,
        "call_cloud_api",
        lambda endpoint, method="GET", client_data_dir=None: {"id": "usr-cloud-user"},
    )
    monkeypatch.setattr(
        auth,
        "list_cloud_projects",
        lambda client_data_dir=None: [{"id": "01M3CLOUDPRJ", "ownerId": "usr-cloud-user"}],
    )

    res = auth.verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3CLOUDPRJ",
        mission_id="01M3CLOUDMIS",
        authoritative_checker=None,
    )
    assert res.edit_authorization == EditAuthorizationStatus.VERIFIED
    assert res.read_only_enforced is False
    assert res.role == "owner"

    # Also verify cross-platform behavior on Linux
    monkeypatch.setattr("sys.platform", "linux")
    res_linux = auth.verify_project_edit_permission(
        client_data_dir=tmp_path,
        project_id="01M3CLOUDPRJ",
        mission_id="01M3CLOUDMIS",
        authoritative_checker=None,
    )
    assert res_linux.edit_authorization == EditAuthorizationStatus.VERIFIED
    assert res_linux.read_only_enforced is False

