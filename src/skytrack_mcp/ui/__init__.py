"""UI observation, window focus, and computer use fallbacks."""

from skytrack_mcp.ui.computer_use import (
    capture_skytrack_screenshot,
    click_relative,
    send_key_name,
    send_keystrokes,
)
from skytrack_mcp.ui.window import (
    focus_skytrack_window,
    get_skytrack_window_bounds,
    is_skytrack_running,
)

__all__ = [
    "focus_skytrack_window",
    "get_skytrack_window_bounds",
    "is_skytrack_running",
    "capture_skytrack_screenshot",
    "click_relative",
    "send_keystrokes",
    "send_key_name",
]
