---
name: skytrack-computer-use
description: Provides semantic UI interaction, window focus management, screencapture verification, and keyboard/mouse fallbacks.
---

# SkyTrack Computer Use Skill

## Purpose
Manages desktop-level interaction with the SkyTrack Electron application window on macOS. Serves as a complementary observation mechanism (capturing window screenshots, verifying UI panels) and fallback control layer when structured API endpoints are insufficient or require visual confirmation.

## Trigger Conditions
- Triggered when visual evidence of the SkyTrack 3D map viewport or Code Editor is required.
- Triggered when window focus is lost or an unhandled modal dialog blocks execution.

## Relevant MCP Tools
- `tool_skytrack_focus()`: Activates the SkyTrack process and brings its window to the foreground.
- `tool_ui_snapshot(file_path)`: Captures high-resolution PNG screenshot of the window bounding box.
- `tool_ui_click(rel_x, rel_y)`: Sends normalized coordinate mouse click (0.0 to 1.0) within the window.
- `tool_ui_key(key_name)`: Sends special keys (`escape`, `return`, `tab`, `space`).
- `tool_ui_type(text)`: Enters text into focused input fields.

## Robustness Best Practices
1. **Never use hard-coded screen coordinates:** Always use relative coordinates `[rel_x, rel_y]` scaled to current window dimensions (`tool_ui_get_state`).
2. **Pre-action Focus:** Always call `tool_skytrack_focus()` before clicking or typing to ensure the window is active.
3. **Postcondition Check:** Follow every critical UI click with a verification check (e.g. check if a modal closed or if the state changed).
4. **Modal Dismissal:** If a prompt or dialog blocks the UI, send `tool_ui_key("escape")` as the first recovery action.
