"""Cross-platform window management and non-mutating process inspection for SkyTrack.

Supports macOS and Linux without hardcoded application paths, self-matching false positives,
or AppleScript launch side-effects.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Any

from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode

# Matches only when ARGV[0] (the executable token itself) is SkyTrack, skytrack, or SkyTrack*.AppImage
_EXECUTABLE_TOKEN_PATTERN = re.compile(
    r"^(?:(?:/[^\s/]+)+/)?(?:SkyTrack|skytrack)(?:(?:-[0-9][0-9A-Za-z._-]*)?\.AppImage)?$"
)

# Excludes child renderer/GPU helper processes and simulation/MCP flags
_EXCLUDED_ARG_MARKERS = (
    "skytrack-mcp",
    "skytrack_mcp",
    "pytest",
    "skytrack-simulation",
    "skytrack-deamon",
    "--type=",
)


def _is_skytrack_desktop_process_line(cmd_line: str) -> bool:
    """Return True if and only if ARGV[0] of cmd_line is the main SkyTrack Desktop executable."""
    line = cmd_line.strip()
    if not line:
        return False

    lower = line.lower()
    if any(marker in lower for marker in _EXCLUDED_ARG_MARKERS):
        return False

    tokens = line.split()
    if not tokens:
        return False

    # If output includes a leading PID column, skip the numeric token
    exe_token = tokens[1] if (len(tokens) > 1 and tokens[0].isdigit()) else tokens[0]
    return bool(_EXECUTABLE_TOKEN_PATTERN.match(exe_token))


def is_skytrack_running() -> bool:
    """Check if SkyTrack desktop application is currently running on this machine.

    Inspects process command lines and matches only when ARGV[0] is the SkyTrack Desktop binary.
    """
    try:
        res = subprocess.run(
            ["ps", "-ax", "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if res.returncode != 0:
            return False
        return any(_is_skytrack_desktop_process_line(line) for line in res.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def focus_skytrack_window() -> dict[str, Any]:
    """Bring SkyTrack application window to the foreground."""
    if not is_skytrack_running():
        raise SkyTrackError(
            SkyTrackErrorCode.SKYTRACK_NOT_RUNNING,
            "SkyTrack is not running on this machine.",
            suggested_action="Launch SkyTrack desktop application.",
        )

    if sys.platform == "darwin":
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
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            if "SUCCESS" in res.stdout:
                return {"focused": True, "app": "SkyTrack"}
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        if shutil.which("wmctrl"):
            try:
                res = subprocess.run(["wmctrl", "-a", "SkyTrack"], capture_output=True, check=False)
                if res.returncode == 0:
                    return {"focused": True, "app": "SkyTrack"}
            except OSError:
                pass

    return {"focused": False, "app": "SkyTrack", "reason": "Focus automation unavailable on this platform."}


def get_skytrack_window_bounds() -> dict[str, Any] | None:
    """Retrieve position and dimensions [x, y, width, height] of SkyTrack main window.

    Guaranteed non-mutating: never calls 'launch' or activates inactive windows.
    Returns None if SkyTrack is not running or window querying is unsupported.
    """
    if not is_skytrack_running():
        return None

    if sys.platform == "darwin":
        # Strictly query existing process without 'launch' command
        script = """
        tell application "System Events"
            if exists (process "SkyTrack") then
                tell process "SkyTrack"
                    if (count of windows) > 0 then
                        set w to first window
                        set p to position of w
                        set s to size of w
                        return (item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string)
                    else
                        return "NO_WINDOWS"
                    end if
                end tell
            else
                return "NOT_RUNNING"
            end if
        end tell
        """
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            out = res.stdout.strip()
            if "," in out:
                parts = [int(float(v.strip())) for v in out.split(",")]
                return {
                    "x": parts[0],
                    "y": parts[1],
                    "width": parts[2],
                    "height": parts[3],
                }
        except (OSError, ValueError):
            return None

    elif sys.platform.startswith("linux"):
        # On Linux, query xdotool if available in X11 session
        if shutil.which("xdotool"):
            try:
                win_search = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", "SkyTrack"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                win_ids = win_search.stdout.strip().split()
                if win_ids:
                    geom = subprocess.run(
                        ["xdotool", "getwindowgeometry", "--shell", win_ids[0]],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    data: dict[str, int] = {}
                    for line in geom.stdout.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            if k.lower() in ("x", "y", "width", "height"):
                                data[k.lower()] = int(v)
                    if all(k in data for k in ("x", "y", "width", "height")):
                        return data
            except (OSError, ValueError):
                return None

    return None
