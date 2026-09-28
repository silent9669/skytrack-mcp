"""Harvests simulation logs, authentic SkyTrack execution reports, media files, and telemetry."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from skytrack_mcp.clients.docker_exec import (
    fetch_live_mavlink_telemetry,
    read_uav_python_logs,
)
from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.mission.parser import parse_ui_mission


def _execution_entries(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = report_data.get("execution_report")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _select_execution_entry(
    report_data: dict[str, Any], execution_id: str | None = None
) -> dict[str, Any] | None:
    entries = _execution_entries(report_data)
    if execution_id is not None:
        return next(
            (entry for entry in entries if str(entry.get("execution_id", "")) == str(execution_id)),
            None,
        )
    return entries[-1] if entries else None


def is_synthetic_report(
    report_data: dict[str, Any],
    file_path: Path | None = None,
    execution_id: str | None = None,
) -> bool:
    """Return True when the selected report or execution has synthetic provenance."""
    if file_path is not None:
        fname = file_path.name.lower()
        if fname.startswith(("synthetic-", "mock-")):
            return True

    meta = report_data.get("execution_metadata") or {}
    if str(report_data.get("report_provenance", "")).lower() in {"synthetic", "synthetic_only"}:
        return True
    if str(meta.get("provenance", "")).lower() == "synthetic":
        return True
    if str(meta.get("source", "")) == "simulate_mission_to_execution_report":
        return True

    entry = _select_execution_entry(report_data, execution_id)
    if entry is None:
        return False
    summary = entry.get("status_summary") or {}
    if str(summary.get("provenance", "")).lower() == "synthetic":
        return True
    # Signatures specific to runner.py simulate_mission_to_execution_report:
    if "actions_defined" in summary:
        return True
    if summary.get("min_ground_speed") == 0.002:
        return True

    for ev in entry.get("execution_events", []):
        st = str((ev.get("data") or {}).get("status", ""))
        if st.startswith("Navigating to WP "):
            return True

    return False


def find_authentic_report_file(
    mis_dir: Path,
    execution_id: str | None = None,
    mission_id: str | None = None,
) -> Path | None:
    """Find native skytrack-mission-report*.json for an optional execution ID.

    flight_report.json is a derived summary written by harvest_flight_report, not a native execution report.
    """
    if not mis_dir.exists():
        return None

    candidates = sorted(mis_dir.glob("skytrack-mission-report*.json"), reverse=True)

    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if mission_id is not None and str((data.get("execution_metadata") or {}).get("mission_id", "")) != str(mission_id):
            continue
        selected_entry = _select_execution_entry(data, execution_id)
        if selected_entry is None:
            continue
        selected_id = str(selected_entry.get("execution_id", "")) or None if selected_entry else None
        if is_synthetic_report(data, candidate, execution_id=selected_id):
            continue
        return candidate

    return None


def _read_local_execution_logs(logs_dir: Path, execution_id: str | None) -> dict[str, str]:
    """Read one mission-local log file, preferring a filename tied to the selected execution."""
    candidates = sorted(
        [path for path in logs_dir.glob("**/*") if path.is_file() and path.suffix.lower() in {".log", ".txt", ".out"}],
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    ) if logs_dir.exists() else []
    if execution_id is not None:
        for path in reversed(candidates):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            markers = [
                index
                for index, line in enumerate(lines)
                if any(name in line.lower() for name in ("execution_id", "exec_id"))
            ]
            if markers:
                for marker_index, next_marker in zip(markers, [*markers[1:], len(lines)], strict=True):
                    if execution_id in lines[marker_index]:
                        return {"logs": "\n".join(lines[marker_index:next_marker])}
                continue
            if execution_id in str(path.relative_to(logs_dir)):
                return {"logs": text}
        return {"logs": ""}
    if not candidates:
        return {"logs": ""}
    try:
        return {"logs": candidates[-1].read_text(encoding="utf-8", errors="replace")}
    except OSError:
        return {"logs": ""}


def _report_telemetry(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Extract only telemetry explicitly persisted with the selected report entry."""
    if not entry:
        return {}
    aliases = {
        "battery_percentage": {"battery_percentage"},
        "connected": {"connected"},
        "is_armed": {"is_armed"},
        "landed_state": {"landed_state"},
        "flight_mode": {"flight_mode"},
        "local_enu_m": {"local_enu_m", "final_enu_position"},
    }
    found: dict[str, Any] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                for normalized, names in aliases.items():
                    if key in names:
                        found[normalized] = child
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(entry)
    return found


def _execution_timestamp(entry: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    summary = entry.get("status_summary") or {}
    if entry.get("timestamp"):
        return str(entry["timestamp"])
    if summary.get("end_time"):
        return str(summary["end_time"])
    events = entry.get("execution_events") or []
    if events and isinstance(events[-1], dict) and events[-1].get("timestamp"):
        return str(events[-1]["timestamp"])
    return str(summary.get("start_time")) if summary.get("start_time") else None


def harvest_mission_report_data(
    mission_id: str,
    project_id: str,
    client_data_dir: Path = CLIENT_DATA_DIR,
    execution_id: str | None = None,
    allow_live_telemetry: bool = False,
) -> dict[str, Any]:
    """Compile flight report data from mission-local evidence, optionally including live telemetry."""
    mis_dir = client_data_dir / f"prj-{project_id}" / f"mis-{mission_id}"
    media_dir = mis_dir / "media"
    logs_dir = mis_dir / "logs"

    # 1. Read mission definition
    mission_file = mis_dir / "mission.json"
    plan_file = mis_dir / "plan.json"
    script_file = mis_dir / "script.py"

    m_json = json.loads(mission_file.read_text(encoding="utf-8")) if mission_file.exists() else {}
    p_json = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    s_text = script_file.read_text(encoding="utf-8") if script_file.exists() else ""

    canonical = parse_ui_mission(project_id, mission_id, m_json, p_json, s_text)

    # 2. Select the exact execution entry from a report belonging to this mission.
    report_files = sorted(
        [*mis_dir.glob("skytrack-mission-report*.json"), *mis_dir.glob("synthetic-mission-report*.json")],
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    ) if mis_dir.exists() else []
    selected_report_file: Path | None = None
    native_report_data: dict[str, Any] | None = None
    selected_entry: dict[str, Any] | None = None
    for candidate in reversed(report_files):
        try:
            candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(candidate_data, dict):
            continue
        metadata = candidate_data.get("execution_metadata") or {}
        if str(metadata.get("mission_id", "")) != str(mission_id):
            continue
        candidate_entry = _select_execution_entry(candidate_data, execution_id)
        if execution_id is not None and candidate_entry is None:
            continue
        if candidate_entry is None and execution_id is None:
            continue
        selected_report_file = candidate
        native_report_data = candidate_data
        selected_entry = candidate_entry
        break

    selected_execution_id = (
        str(selected_entry.get("execution_id"))
        if selected_entry and selected_entry.get("execution_id") is not None
        else None
    )
    selected_is_synthetic = bool(
        native_report_data
        and is_synthetic_report(native_report_data, selected_report_file, selected_execution_id)
    )
    rep_file = selected_report_file if selected_report_file and not selected_is_synthetic else None
    if rep_file is None and selected_report_file is None:
        rep_file = find_authentic_report_file(mis_dir, execution_id=execution_id, mission_id=mission_id)
    if selected_is_synthetic and selected_report_file and selected_report_file.name.startswith("synthetic-mission-report"):
        report_provenance = "synthetic_only"
    elif selected_is_synthetic:
        report_provenance = "synthetic"
    else:
        report_provenance = "authentic" if rep_file else "none"

    # Parse authentic execution events and summary
    execution_status = "UNKNOWN"
    execution_duration_s = 0.0
    average_ground_speed = None
    waypoints_reached: list[dict[str, Any]] = []
    payload_triggers: list[dict[str, Any]] = []
    flight_mode_changes: list[str] = []
    raw_events: list[dict[str, Any]] = []
    landing_completed = False
    observed_takeoff_altitude_m: float | None = None

    if native_report_data and not selected_is_synthetic:
        exec_meta = native_report_data.get("execution_metadata", {})
        execution_status = exec_meta.get("status", "COMPLETED")
        execution_duration_s = float(exec_meta.get("duration", 0.0))

        report_entries = native_report_data.get("execution_report", [])
        if report_entries and isinstance(report_entries, list):
            entry = next(
                (item for item in report_entries if str(item.get("execution_id", "")) == str(execution_id)),
                None,
            ) if execution_id is not None else report_entries[-1]
            if entry is None:
                raise ValueError(f"Execution {execution_id} was not found in {rep_file}")
            summary = entry.get("status_summary", {})
            if "final_status" in summary:
                execution_status = summary["final_status"]
            if "duration_seconds" in summary:
                execution_duration_s = float(summary["duration_seconds"])
            if "average_ground_speed" in summary:
                average_ground_speed = float(summary["average_ground_speed"])

            raw_events = entry.get("execution_events", [])
            landing_completed = any(
                ev.get("event") in ("RTL", "LAND")
                and (ev.get("data") or {}).get("phase") == "completed"
                for ev in raw_events
            )
            for ev in raw_events:
                ev_name = ev.get("event")
                ev_data = ev.get("data", {})
                if ev_name == "TAKEOFF" and observed_takeoff_altitude_m is None and ev_data.get("target_altitude") is not None:
                    observed_takeoff_altitude_m = float(ev_data["target_altitude"])
                if ev_name == "WAYPOINT_REACHED":
                    waypoints_reached.append(ev_data)
                elif ev_name == "PAYLOAD_TRIGGER":
                    payload_triggers.append(ev_data)
                elif ev_name == "FLIGHT_MODE_CHANGE":
                    flight_mode_changes.append(ev_data.get("mode", ""))

            ball_drops = [ev.get("data", {}) for ev in raw_events if ev.get("event") == "BALL_DROP"]
            if ball_drops:
                payload_triggers = ball_drops

    # 3. Collect media captures
    captures: list[str] = []
    if (media_dir / "captures").exists():
        captures = sorted(f.name for f in (media_dir / "captures").glob("*") if f.is_file())

    recordings: list[str] = []
    if (media_dir / "recordings").exists():
        recordings = sorted(f.name for f in (media_dir / "recordings").glob("*") if f.is_file())

    # 4. Read runtime sources only when explicitly requested; offline reads stay mission-local.
    if allow_live_telemetry:
        uav_logs = read_uav_python_logs(tail_lines=150)
        telem = fetch_live_mavlink_telemetry()
    else:
        uav_logs = _read_local_execution_logs(logs_dir, selected_execution_id)
        telem = _report_telemetry(selected_entry)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    execution_timestamp = _execution_timestamp(selected_entry)
    native_metadata = (native_report_data or {}).get("execution_metadata") or {}

    report_dict: dict[str, Any] = {
        "report_id": f"rep-{mission_id}-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}",
        "timestamp": now_iso,
        "selected_execution_id": selected_execution_id,
        "execution_timestamp": execution_timestamp,
        "project_id": project_id,
        "mission_id": mission_id,
        "world": native_metadata.get("world", canonical.world),
        "vehicle": native_metadata.get("vehicle", canonical.vehicle),
        "target_speed_m_s": canonical.target_speed,
        "takeoff_altitude_m": canonical.takeoff_altitude,
        "observed_takeoff_altitude_m": observed_takeoff_altitude_m,
        "total_planned_waypoints": len(canonical.waypoints),
        "total_planned_actions": len(canonical.raw_actions),
        "execution_status": execution_status,
        "landing_completed": landing_completed,
        "execution_duration_s": execution_duration_s,
        "average_ground_speed_m_s": average_ground_speed,
        "waypoints_reached_count": len(waypoints_reached),
        "waypoints_reached": waypoints_reached,
        "payload_triggers_count": len(payload_triggers),
        "payload_triggers": payload_triggers,
        "flight_mode_changes": flight_mode_changes,
        "authentic_report_file": rep_file.name if rep_file else None,
        "synthetic_report_file": selected_report_file.name if selected_is_synthetic and selected_report_file else None,
        "report_provenance": report_provenance,
        "telemetry_state": {
            "connected": telem.get("connected", False),
            "is_armed": telem.get("is_armed"),
            "landed_state": telem.get("landed_state", "UNKNOWN"),
            "flight_mode": telem.get("flight_mode", "UNKNOWN"),
            "battery_percentage": telem.get("battery_percentage"),
            "final_enu_position": telem.get("local_enu_m", telem.get("final_enu_position")),
        },
        "media_output": {
            "captures_count": len(captures),
            "captures": captures,
            "recordings_count": len(recordings),
            "recordings": recordings,
        },
        "execution_logs_tail": uav_logs.get("logs", ""),
    }

    return report_dict


def render_markdown_flight_report(report_data: dict[str, Any]) -> str:
    """Generate human and AI readable Markdown Mission Report."""
    telem = report_data.get("telemetry_state", {})
    media = report_data.get("media_output", {})
    reached_wps = report_data.get("waypoints_reached", [])
    payloads = report_data.get("payload_triggers", [])

    reached_str = f"{len(reached_wps)} reached"
    if reached_wps:
        reached_str += " (" + ", ".join(f"WP#{w.get('wp_index', i+1)}:[{w.get('x',0):.1f},{w.get('y',0):.1f}]" for i, w in enumerate(reached_wps[:5])) + ")"

    provenance = report_data.get("report_provenance", "none")
    return f"""# SkyTrack Flight Summary ({provenance})

**Report ID:** `{report_data['report_id']}`
**Timestamp:** `{report_data['timestamp']}`
**Mission:** `{report_data['mission_id']}` (Project `{report_data['project_id']}`)
**World:** `{report_data['world']}` | **Vehicle:** `{report_data['vehicle']}`
**Native Report Source:** `{report_data.get('authentic_report_file') or 'Unavailable'}`

---

## 1. Flight Execution Overview
- **Final Status:** `{report_data.get('execution_status', 'UNKNOWN')}`
- **Flight Duration:** {report_data.get('execution_duration_s', 0.0)} seconds
- **Average Ground Speed:** {report_data.get('average_ground_speed_m_s')} m/s
- **Landed State:** `{telem.get('landed_state')}`
- **Armed:** `{telem.get('is_armed')}`
- **Battery Remaining:** `{telem.get('battery_percentage')}%`

## 2. Mission Plan vs. Reached Statistics
- **Planned Waypoints:** {report_data['total_planned_waypoints']}
- **Waypoints Reached:** {reached_str}
- **Planned Actions:** {report_data['total_planned_actions']}
- **Payload Triggers Executed:** {len(payloads)}
- **Cruise Altitude:** {report_data['takeoff_altitude_m']} m

## 3. Sensor & Payload Outputs
- **Captured Images ({media.get('captures_count', 0)}):** {', '.join(media.get('captures', [])) or 'None'}
- **Video Recordings ({media.get('recordings_count', 0)}):** {', '.join(media.get('recordings', [])) or 'None'}

## 4. Onboard Execution Logs
```text
{report_data.get('execution_logs_tail', 'No logs recorded.')}
```
"""
