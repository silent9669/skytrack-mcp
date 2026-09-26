"""Harvests simulation logs, authentic SkyTrack execution reports, media files, and telemetry."""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from skytrack_mcp.clients.docker_exec import fetch_live_mavlink_telemetry, read_uav_python_logs
from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.mission.parser import parse_ui_mission


def find_authentic_report_file(mis_dir: Path) -> Optional[Path]:
    """Find authentic skytrack-mission-report*.json or flight_report.json file in mission directory."""
    if not mis_dir.exists():
        return None

    # Priority 1: skytrack-mission-report.json or skytrack-mission-report-*.json
    reports = sorted(mis_dir.glob("skytrack-mission-report*.json"))
    if reports:
        return reports[-1]

    # Priority 2: flight_report.json
    flight_rep = mis_dir / "flight_report.json"
    if flight_rep.exists():
        return flight_rep

    return None


def harvest_mission_report_data(
    mission_id: str,
    project_id: str,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Compile structured flight report data from authentic SkyTrack report files, logs, and telemetry."""
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

    # 2. Check for authentic SkyTrack execution report JSON
    rep_file = find_authentic_report_file(mis_dir)
    native_report_data: Optional[Dict[str, Any]] = None
    if rep_file and rep_file.exists():
        try:
            native_report_data = json.loads(rep_file.read_text(encoding="utf-8"))
        except Exception:
            native_report_data = None

    # Parse authentic execution events and summary
    execution_status = "UNKNOWN"
    execution_duration_s = 0.0
    average_ground_speed = None
    waypoints_reached: List[Dict[str, Any]] = []
    payload_triggers: List[Dict[str, Any]] = []
    flight_mode_changes: List[str] = []
    raw_events: List[Dict[str, Any]] = []

    if native_report_data:
        exec_meta = native_report_data.get("execution_metadata", {})
        execution_status = exec_meta.get("status", "COMPLETED")
        execution_duration_s = float(exec_meta.get("duration", 0.0))

        report_entries = native_report_data.get("execution_report", [])
        if report_entries and isinstance(report_entries, list):
            entry = report_entries[0]
            summary = entry.get("status_summary", {})
            if "final_status" in summary:
                execution_status = summary["final_status"]
            if "duration_seconds" in summary:
                execution_duration_s = float(summary["duration_seconds"])
            if "average_ground_speed" in summary:
                average_ground_speed = float(summary["average_ground_speed"])

            raw_events = entry.get("execution_events", [])
            for ev in raw_events:
                ev_name = ev.get("event")
                ev_data = ev.get("data", {})
                if ev_name == "WAYPOINT_REACHED":
                    waypoints_reached.append(ev_data)
                elif ev_name == "PAYLOAD_TRIGGER":
                    payload_triggers.append(ev_data)
                elif ev_name == "FLIGHT_MODE_CHANGE":
                    flight_mode_changes.append(ev_data.get("mode", ""))

    # 3. Collect media captures
    captures: List[str] = []
    if (media_dir / "captures").exists():
        captures = sorted(f.name for f in (media_dir / "captures").glob("*") if f.is_file())

    recordings: List[str] = []
    if (media_dir / "recordings").exists():
        recordings = sorted(f.name for f in (media_dir / "recordings").glob("*") if f.is_file())

    # 4. Read autonomy logs and instantaneous telemetry
    uav_logs = read_uav_python_logs(tail_lines=150)
    telem = fetch_live_mavlink_telemetry()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    report_dict: Dict[str, Any] = {
        "report_id": f"rep-{mission_id}-{int(datetime.datetime.now().timestamp())}",
        "timestamp": now_iso,
        "project_id": project_id,
        "mission_id": mission_id,
        "world": canonical.world,
        "vehicle": canonical.vehicle,
        "target_speed_m_s": canonical.target_speed,
        "takeoff_altitude_m": canonical.takeoff_altitude,
        "total_planned_waypoints": len(canonical.waypoints),
        "total_planned_actions": len(canonical.raw_actions),
        "execution_status": execution_status,
        "execution_duration_s": execution_duration_s,
        "average_ground_speed_m_s": average_ground_speed,
        "waypoints_reached_count": len(waypoints_reached),
        "waypoints_reached": waypoints_reached,
        "payload_triggers_count": len(payload_triggers),
        "payload_triggers": payload_triggers,
        "flight_mode_changes": flight_mode_changes,
        "authentic_report_file": rep_file.name if rep_file else None,
        "telemetry_state": {
            "connected": telem.get("connected", False),
            "is_armed": telem.get("is_armed", False),
            "landed_state": telem.get("landed_state", "UNKNOWN" if execution_status == "UNKNOWN" else "ON_GROUND"),
            "flight_mode": telem.get("flight_mode", "UNKNOWN" if execution_status == "UNKNOWN" else "HOLD"),
            "battery_percentage": telem.get("battery_percentage", 100.0 if execution_status == "COMPLETED" else None),
            "final_enu_position": telem.get("local_enu_m"),
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


def render_markdown_flight_report(report_data: Dict[str, Any]) -> str:
    """Generate human and AI readable Markdown Mission Report."""
    telem = report_data.get("telemetry_state", {})
    media = report_data.get("media_output", {})
    reached_wps = report_data.get("waypoints_reached", [])
    payloads = report_data.get("payload_triggers", [])

    reached_str = f"{len(reached_wps)} reached"
    if reached_wps:
        reached_str += " (" + ", ".join(f"WP#{w.get('wp_index', i+1)}:[{w.get('x',0):.1f},{w.get('y',0):.1f}]" for i, w in enumerate(reached_wps[:5])) + ")"

    return f"""# SkyTrack Official Flight Execution Report

**Report ID:** `{report_data['report_id']}`
**Timestamp:** `{report_data['timestamp']}`
**Mission:** `{report_data['mission_id']}` (Project `{report_data['project_id']}`)
**World:** `{report_data['world']}` | **Vehicle:** `{report_data['vehicle']}`
**Authentic Report Source:** `{report_data.get('authentic_report_file') or 'Live Telemetry & Logs'}`

---

## 1. Flight Execution Overview
- **Final Status:** `{report_data.get('execution_status', 'UNKNOWN')}`
- **Flight Duration:** {report_data.get('execution_duration_s', 0.0)} seconds
- **Average Ground Speed:** {report_data.get('average_ground_speed_m_s') or report_data.get('target_speed_m_s')} m/s
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
