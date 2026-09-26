"""Computer use observation, window screenshots, and semantic UI interaction fallbacks."""

from __future__ import annotations

import base64
import datetime
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.ui.window import focus_skytrack_window, get_skytrack_window_bounds


def capture_skytrack_screenshot(
    file_path: Optional[str] = None,
    include_base64: bool = False,
) -> Dict[str, Any]:
    """Capture a screenshot of the SkyTrack window and return metadata (and optional base64 PNG)."""
    bounds = get_skytrack_window_bounds()
    x, y, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]

    target_path = Path(file_path) if file_path else Path(tempfile.mktemp(suffix=".png"))
    target_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["screencapture", "-R", f"{x},{y},{w},{h}", str(target_path)]
    res = subprocess.run(cmd, capture_output=True, check=False)
    if res.returncode != 0 or not target_path.exists():
        raise SkyTrackError(
            SkyTrackErrorCode.UI_STATE_MISMATCH,
            f"Failed to capture SkyTrack window screenshot: {res.stderr.decode()}",
        )

    img_bytes = target_path.read_bytes()
    result: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window_bounds": bounds,
        "saved_path": str(target_path),
        "image_size_bytes": len(img_bytes),
    }
    if include_base64:
        result["base64_png"] = base64.b64encode(img_bytes).decode("utf-8")
    return result


def click_relative(rel_x: float, rel_y: float) -> Dict[str, Any]:
    """Click inside SkyTrack window using normalized coordinates [0.0 .. 1.0]."""
    focus_skytrack_window()
    bounds = get_skytrack_window_bounds()
    abs_x = bounds["x"] + int(bounds["width"] * max(0.0, min(1.0, rel_x)))
    abs_y = bounds["y"] + int(bounds["height"] * max(0.0, min(1.0, rel_y)))

    script = f"""
    tell application "System Events"
        click at {{{abs_x}, {abs_y}}}
    end tell
    """
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    return {
        "clicked": res.returncode == 0,
        "screen_coords": [abs_x, abs_y],
        "relative_coords": [rel_x, rel_y],
    }


def send_keystrokes(text: str) -> Dict[str, Any]:
    """Type text into the currently focused SkyTrack UI element."""
    focus_skytrack_window()
    safe_text = text.replace('"', '\\"')
    script = f"""
    tell application "System Events"
        keystroke "{safe_text}"
    end tell
    """
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    return {"typed": res.returncode == 0, "text_length": len(text)}


def send_key_name(key_name: str) -> Dict[str, Any]:
    """Send special key (e.g. 'return', 'tab', 'escape', 'space')."""
    focus_skytrack_window()
    key_codes = {
        "return": 36,
        "enter": 36,
        "tab": 48,
        "space": 49,
        "delete": 51,
        "escape": 53,
        "up": 126,
        "down": 125,
        "left": 123,
        "right": 124,
    }
    code = key_codes.get(key_name.lower().strip())
    if code is not None:
        script = f'tell application "System Events" to key code {code}'
    else:
        script = f'tell application "System Events" to keystroke "{key_name}"'

    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    return {"key_sent": key_name, "success": res.returncode == 0}
