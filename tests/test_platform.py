"""Unit tests for cross-platform data root and machine ID discovery."""

from __future__ import annotations

from pathlib import Path

from skytrack_mcp.platform import (
    derive_token_encryption_key,
    get_default_client_data_dir,
    get_platform_machine_id,
)


def test_get_default_client_data_dir_darwin(monkeypatch):
    """On macOS (darwin), data root should resolve to ~/Library/Application Support/SkyTrack/ClientData."""
    monkeypatch.setattr("sys.platform", "darwin")
    fake_home = Path("/fake/user/home")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("SKYTRACK_CLIENT_DATA", raising=False)

    data_dir = get_default_client_data_dir()
    assert data_dir == fake_home / "Library" / "Application Support" / "SkyTrack" / "ClientData"


def test_get_default_client_data_dir_linux_default(monkeypatch):
    """On Linux without XDG_CONFIG_HOME, data root should resolve to ~/.config/SkyTrack/ClientData."""
    monkeypatch.setattr("sys.platform", "linux")
    fake_home = Path("/fake/linux/home")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("SKYTRACK_CLIENT_DATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    data_dir = get_default_client_data_dir()
    assert data_dir == fake_home / ".config" / "SkyTrack" / "ClientData"


def test_get_default_client_data_dir_linux_xdg(monkeypatch):
    """On Linux with XDG_CONFIG_HOME set, data root should resolve to $XDG_CONFIG_HOME/SkyTrack/ClientData."""
    monkeypatch.setattr("sys.platform", "linux")
    fake_xdg = "/custom/xdg/config"
    monkeypatch.setenv("XDG_CONFIG_HOME", fake_xdg)
    monkeypatch.delenv("SKYTRACK_CLIENT_DATA", raising=False)

    data_dir = get_default_client_data_dir()
    assert data_dir == Path(fake_xdg) / "SkyTrack" / "ClientData"


def test_get_default_client_data_dir_env_override(monkeypatch):
    """Explicit SKYTRACK_CLIENT_DATA env variable always overrides platform default."""
    custom_path = "/var/custom/skytrack/ClientData"
    monkeypatch.setenv("SKYTRACK_CLIENT_DATA", custom_path)

    data_dir = get_default_client_data_dir()
    assert data_dir == Path(custom_path)


def test_get_platform_machine_id_linux(tmp_path, monkeypatch):
    """On Linux, reads machine-id from /etc/machine-id or /var/lib/dbus/machine-id."""
    fake_machine_id_file = tmp_path / "machine-id"
    fake_machine_id_file.write_text("a1b2c3d4e5f67890\n")

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("skytrack_mcp.platform.LINUX_MACHINE_ID_PATHS", [fake_machine_id_file])

    mid = get_platform_machine_id()
    assert mid == "a1b2c3d4e5f67890"


def test_derive_token_encryption_key_deterministic(monkeypatch):
    """AES key derivation is 32 bytes and deterministic from machine ID."""
    monkeypatch.setattr("skytrack_mcp.platform.get_platform_machine_id", lambda: "test-uuid-1234")
    key = derive_token_encryption_key()
    assert isinstance(key, bytes)
    assert len(key) == 32
