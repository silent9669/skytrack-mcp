"""macOS window management and focus automation for SkyTrack."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, Optional

from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode


def is_skytrack_running() -> bool:
    res = subprocess.run(["pgrep", "-f", "/Applications/SkyTrack.app/Contents/MacOS/SkyTrack"], capture_output=True, check=False)
    return res.returncode == 0


def focus_skytrack_window() -> Dict[str, Any]:
    """Bring SkyTrack application window to the foreground."""
    script = """
    tell application "System Events"
        if exists (process "SkyTrack") then
            tell application "SkyTrack" to activate
            return "SUCCESS"
        else
            return "NOT_RUNNING"
        end if
    end tell
    """
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    out = res.stdout.strip()
    if "NOT_RUNNING" in out or not is_skytrack_running():
        raise SkyTrackError(
            SkyTrackErrorCode.SKYTRACK_NOT_RUNNING,
            "SkyTrack is not running on this machine.",
            suggested_action="Launch SkyTrack.app from /Applications",
        )
    return {"focused": True, "app": "SkyTrack"}


def get_skytrack_window_bounds() -> Dict[str, Any]:
    """Retrieve position and dimensions [x, y, width, height] of SkyTrack main window."""
    script = """
    tell application "System Events"
        launch
        if exists (process "SkyTrack") then
            tell process "SkyTrack"
                set w to first window
                set p to position of w
                set s to size of w
                return (item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string)
            end tell
        else
            return "NOT_RUNNING"
        end if
    end tell
    """
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    out = res.stdout.strip()
    if "NOT_RUNNING" in out or not out or "," not in out:
        raise SkyTrackError(
            SkyTrackErrorCode.WINDOW_NOT_FOUND,
            f"Could not locate SkyTrack window: {res.stderr or out}",
        )
    parts = [int(float(v.strip())) for v in out.split(",")]
    return {
        "x": parts[0],
        "y": parts[1],
        "width": parts[2],
        "height": parts[3],
    }
