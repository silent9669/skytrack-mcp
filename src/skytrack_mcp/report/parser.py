"""Harvests simulation logs, media files, and telemetry to generate normalized flight reports."""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from skytrack_mcp.clients.docker_exec import fetch_live_mavlink_telemetry, read_uav_python_logs
from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.mission.parser import parse_ui_mission


def harvest_mission_report_data(
    mission_id: str,
    project_id: str,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Compile structured flight report data from local files and container states."""
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

    # 2. Collect media captures
    captures: List[str] = []
    if (media_dir / "captures").exists():
        captures = sorted(f.name for f in (media_dir / "captures").glob("*") if f.is_file())

    recordings: List[str] = []
    if (media_dir / "recordings").exists():
        recordings = sorted(f.name for f in (media_dir / "recordings").glob("*") if f.is_file())

    # 3. Read autonomy logs
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
        "telemetry_state": {
            "connected": telem.get("connected", False),
            "is_armed": telem.get("is_armed", False),
            "landed_state": telem.get("landed_state", "UNKNOWN"),
            "flight_mode": telem.get("flight_mode", "UNKNOWN"),
            "battery_percentage": telem.get("battery_percentage"),
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

    return f"""# SkyTrack Official Flight Execution Report

**Report ID:** `{report_data['report_id']}`
**Timestamp:** `{report_data['timestamp']}`
**Mission:** `{report_data['mission_id']}` (Project `{report_data['project_id']}`)
**World:** `{report_data['world']}` | **Vehicle:** `{report_data['vehicle']}`

---

## 1. Flight Execution Overview
- **Landed State:** `{telem.get('landed_state')}`
- **Armed:** `{telem.get('is_armed')}`
- **Flight Mode:** `{telem.get('flight_mode')}`
- **Battery Remaining:** `{telem.get('battery_percentage')}%`
- **Final Position (ENU meters):** `{telem.get('final_enu_position')}`

## 2. Mission Plan Statistics
- **Planned Waypoints:** {report_data['total_planned_waypoints']}
- **Planned Actions:** {report_data['total_planned_actions']}
- **Cruise Speed:** {report_data['target_speed_m_s']} m/s
- **Target Altitude:** {report_data['takeoff_altitude_m']} m

## 3. Sensor & Payload Outputs
- **Captured Images ({media.get('captures_count', 0)}):** {', '.join(media.get('captures', [])) or 'None'}
- **Video Recordings ({media.get('recordings_count', 0)}):** {', '.join(media.get('recordings', [])) or 'None'}

## 4. Onboard Execution Logs
```text
{report_data.get('execution_logs_tail', 'No logs recorded.')}
```
"""
