# SkyTrack Computer Use & UI Automation

## 1. Principles of Computer Use Integration
Per Section 3 of `@GOAL.md`, mouse-coordinate automation is treated as a **complementary observation and recovery fallback**, never the primary mission-construction interface. Structured JSON manipulation (`plan.json`) and GCS Control APIs (`:20002`) are orders of magnitude faster, deterministic, and resilient to UI changes.

## 2. macOS Window Detection & Focus
SkyTrack runs as an Electron application on macOS (`com.getskytrack.client`). The MCP server uses native AppleScript via `osascript` to locate the application:
```applescript
tell application "System Events"
    if exists (process "SkyTrack") then
        tell application "SkyTrack" to activate
    end if
end tell
```

## 3. Normalized Window Coordinates
To prevent screen resolution or display scaling issues (such as Retina 2x scaling), all clicking actions accept normalized relative coordinates:
$$x_{\text{abs}} = x_{\text{window}} + \text{width} \times \text{rel\_x}$$
$$y_{\text{abs}} = y_{\text{window}} + \text{height} \times \text{rel\_y}$$

Where $\text{rel\_x}, \text{rel\_y} \in [0.0, 1.0]$.

## 4. Visual Evidence Capture
The `tool_ui_snapshot` tool invokes the macOS native `screencapture -R <x,y,w,h> <file>` utility targeting only the active SkyTrack window rectangle, saving disk space and eliminating desktop clutter from multi-monitor setups.
