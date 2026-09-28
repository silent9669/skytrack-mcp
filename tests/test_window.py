"""Unit tests for cross-platform, non-mutating window and process inspection."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from skytrack_mcp.ui.window import (
    _is_skytrack_desktop_process_line,
    get_skytrack_window_bounds,
    is_skytrack_running,
)


@pytest.mark.parametrize(
    "cmd_line, expected",
    [
        # Genuine Desktop Executables:
        ("/Applications/SkyTrack.app/Contents/MacOS/SkyTrack", True),
        ("/Applications/SkyTrack.app/Contents/MacOS/SkyTrack --no-sandbox", True),
        ("/opt/SkyTrack/skytrack", True),
        ("/usr/bin/SkyTrack", True),
        ("SkyTrack", True),
        ("skytrack", True),
        ("/home/ubuntu/SkyTrack-1.2.6.AppImage", True),
        ("/home/ubuntu/SkyTrack.AppImage", True),
        # False-Positive Protections (tools with SkyTrack paths in arguments):
        ("custom-helper --file /usr/bin/SkyTrack", False),
        ("some-tool /Applications/SkyTrack.app/Contents/MacOS/SkyTrack", False),
        ("tail -f /opt/SkyTrack/skytrack", False),
        ("cat /Applications/SkyTrack.app/Contents/Info.plist", False),
        ("lldb /Applications/SkyTrack.app/Contents/MacOS/SkyTrack", False),
        # Self-Matching Exclusions:
        ("/usr/local/bin/skytrack-mcp", False),
        ("python3 -m skytrack_mcp.server", False),
        ("/Users/user/.venv/bin/python /Users/user/.venv/bin/skytrack-mcp", False),
        ("uv run pytest /home/ubuntu/skytrack-mcp/tests", False),
        ("pytest tests/test_window.py", False),
        ("docker run skytrack-simulation-gazebo-1", False),
        ("docker logs skytrack-deamon-gcs-backend-1", False),
        # Child Helper Process Exclusions:
        ("/Applications/SkyTrack.app/Contents/MacOS/SkyTrack --type=renderer", False),
        ("/Applications/SkyTrack.app/Contents/MacOS/SkyTrack --type=gpu-process", False),
    ],
)
def test_is_skytrack_desktop_process_line_filtering(cmd_line: str, expected: bool):
    """Verify only authentic desktop binaries match, while MCP servers/tests/helpers are excluded."""
    assert _is_skytrack_desktop_process_line(cmd_line) is expected


def test_is_skytrack_running_excludes_mcp_and_pytest(monkeypatch: pytest.MonkeyPatch):
    """When only the MCP server and pytest are running, is_skytrack_running must return False."""
    ps_output = """
    1001 /bin/zsh
    1002 python3 -m skytrack_mcp.server
    1003 uv run pytest /Users/phucdang/Documents/skytrack-mcp/tests
    1004 /usr/local/bin/skytrack-mcp
    1005 custom-helper --file /usr/bin/SkyTrack
    """
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(["ps"], 0, ps_output, ""))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert is_skytrack_running() is False


def test_is_skytrack_running_detects_desktop_app(monkeypatch: pytest.MonkeyPatch):
    """When authentic SkyTrack desktop is running, returns True."""
    ps_output = """
    1001 /bin/zsh
    1002 /Applications/SkyTrack.app/Contents/MacOS/SkyTrack
    1003 python3 -m skytrack_mcp.server
    """
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(["ps"], 0, ps_output, ""))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert is_skytrack_running() is True


def test_is_skytrack_running_detects_linux_appimage(monkeypatch: pytest.MonkeyPatch):
    """When authentic SkyTrack AppImage is running on Linux, returns True."""
    ps_output = """
    1001 /bin/bash
    1002 /home/ubuntu/Applications/SkyTrack-1.2.6.AppImage
    """
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(["ps"], 0, ps_output, ""))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert is_skytrack_running() is True


def test_get_skytrack_window_bounds_when_not_running():
    """When app is not running, window bounds query returns None without invoking osascript."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("skytrack_mcp.ui.window.is_skytrack_running", lambda: False)
        mock_sub = MagicMock()
        mp.setattr(subprocess, "run", mock_sub)

        bounds = get_skytrack_window_bounds()
        assert bounds is None
        mock_sub.assert_not_called()


def test_get_skytrack_window_bounds_macos_no_launch(monkeypatch: pytest.MonkeyPatch):
    """When querying bounds on macOS, the script must NOT execute 'launch'."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("skytrack_mcp.ui.window.is_skytrack_running", lambda: True)

    executed_scripts = []

    def fake_run(cmd, **_kw):
        if cmd[0] == "osascript":
            executed_scripts.append(cmd[2])
            return subprocess.CompletedProcess(cmd, 0, "100, 200, 800, 600\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    bounds = get_skytrack_window_bounds()
    assert bounds == {"x": 100, "y": 200, "width": 800, "height": 600}
    assert len(executed_scripts) == 1
    # Verify no 'launch' command is present in the AppleScript
    assert "\n        launch\n" not in executed_scripts[0]
