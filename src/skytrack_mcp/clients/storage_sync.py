"""Synchronizes missions, visual routes (plan.json), metadata (mission.json), and scripts (script.py)
with the local SkyTrack Electron application storage."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skytrack_mcp.config import CLIENT_DATA_DIR


def list_all_missions(client_data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return all missions across all projects in ClientData, sorted by most recently modified."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    missions: List[Dict[str, Any]] = []
    if not client_data_dir.exists():
        return missions

    for prj_dir in client_data_dir.glob("prj-*"):
        if not prj_dir.is_dir():
            continue
        project_id = prj_dir.name.removeprefix("prj-")
        for mis_dir in prj_dir.glob("mis-*"):
            if not mis_dir.is_dir():
                continue
            mission_id = mis_dir.name.removeprefix("mis-")
            mission_file = mis_dir / "mission.json"
            plan_file = mis_dir / "plan.json"
            script_file = mis_dir / "script.py"

            metadata: Dict[str, Any] = {}
            if mission_file.exists():
                try:
                    metadata = json.loads(mission_file.read_text(encoding="utf-8"))
                except Exception:
                    metadata = {}

            plan_data: Dict[str, Any] = {}
            if plan_file.exists():
                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                except Exception:
                    plan_data = {}

            sequences = plan_data.get("sequences", [])
            action_count = sum(len(seq.get("actions", [])) for seq in sequences)

            mtime = max(
                (f.stat().st_mtime for f in (mission_file, plan_file, script_file) if f.exists()),
                default=mis_dir.stat().st_mtime,
            )

            missions.append(
                {
                    "project_id": project_id,
                    "mission_id": mission_id,
                    "path": str(mis_dir),
                    "world": metadata.get("world", "default"),
                    "vehicle": metadata.get("vehicle", "x500_livox_mid_360"),
                    "code_mode": metadata.get("codeMode", False),
                    "target_speed": metadata.get("targetSpeed", 2.0),
                    "takeoff_altitude": metadata.get("takeoffAltitude", 2.0),
                    "safety_option": metadata.get("safetyOption", "avoid"),
                    "end_action": metadata.get("end", {}).get("type", "rtl"),
                    "spawn_location": plan_data.get("spawnLocation", [0.0, 0.0, 0.0]),
                    "action_count": action_count,
                    "has_script": script_file.exists(),
                    "last_modified": mtime,
                }
            )

    missions.sort(key=lambda m: m["last_modified"], reverse=True)
    return missions


def resolve_mission_dir(
    mission_id: Optional[str] = None,
    client_data_dir: Optional[Path] = None,
) -> Tuple[Path, str, str]:
    """Resolve (mission_dir, project_id, mission_id).
    If mission_id is None, returns the most recently modified mission."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    missions = list_all_missions(client_data_dir)
    if not missions:
        raise FileNotFoundError(f"No SkyTrack missions found in {client_data_dir}")

    if mission_id:
        clean_id = mission_id.removeprefix("mis-")
        for m in missions:
            if m["mission_id"] == clean_id:
                return Path(m["path"]), m["project_id"], m["mission_id"]
        raise FileNotFoundError(
            f"Mission '{mission_id}' not found. Available: {[m['mission_id'] for m in missions]}"
        )

    latest = missions[0]
    return Path(latest["path"]), latest["project_id"], latest["mission_id"]


def read_mission_details(
    mission_id: Optional[str] = None,
    client_data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read full mission.json, plan.json, and script.py for a mission."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id, client_data_dir)
    mission_file = mis_dir / "mission.json"
    plan_file = mis_dir / "plan.json"
    script_file = mis_dir / "script.py"

    mission_json = (
        json.loads(mission_file.read_text(encoding="utf-8")) if mission_file.exists() else {}
    )
    plan_json = (
        json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    )
    script_py = script_file.read_text(encoding="utf-8") if script_file.exists() else ""

    return {
        "project_id": prj_id,
        "mission_id": mis_id,
        "path": str(mis_dir),
        "mission": mission_json,
        "plan": plan_json,
        "script": script_py,
    }


def write_visual_route(
    waypoints: List[Dict[str, Any]],
    mission_id: Optional[str] = None,
    spawn_location: Optional[List[float]] = None,
    takeoff_altitude: float = 2.0,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: Optional[str] = None,
    vehicle: Optional[str] = None,
    client_data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Write a visual route into plan.json and update mission.json for the SkyTrack UI.

    Each item in `waypoints` can be:
      - {"x": float, "y": float, "z": float} (or {"data": [x, y, z]}) -> creates a "navigate" action
      - Optionally with {"after_action": "drop-ball" | "start-recording-video" | "stop-recording-video" | "take-photo"}
      - Or a direct UI action {"type": "drop-ball" | "navigate" | ..., "data": [x, y, z]}
    """
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id, client_data_dir)
    mission_file = mis_dir / "mission.json"
    plan_file = mis_dir / "plan.json"

    existing_mission: Dict[str, Any] = {}
    if mission_file.exists():
        try:
            existing_mission = json.loads(mission_file.read_text(encoding="utf-8"))
        except Exception:
            existing_mission = {}

    existing_plan: Dict[str, Any] = {}
    if plan_file.exists():
        try:
            existing_plan = json.loads(plan_file.read_text(encoding="utf-8"))
        except Exception:
            existing_plan = {}

    ui_actions: List[Dict[str, Any]] = []
    for wp in waypoints:
        wp_type = wp.get("type", "navigate")
        if wp_type in ("navigate", "waypoint") or ("x" in wp and "y" in wp):
            if "data" in wp and isinstance(wp["data"], list) and len(wp["data"]) == 3:
                coords = [float(wp["data"][0]), float(wp["data"][1]), float(wp["data"][2])]
            else:
                coords = [
                    float(wp.get("x", 0.0)),
                    float(wp.get("y", 0.0)),
                    float(wp.get("z", takeoff_altitude)),
                ]
            ui_actions.append(
                {
                    "type": "navigate",
                    "id": str(wp.get("id") or uuid.uuid4()),
                    "data": coords,
                }
            )
            after_action = wp.get("after_action")
            if after_action:
                ui_actions.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": after_action,
                    }
                )
        else:
            action_entry: Dict[str, Any] = {
                "id": str(wp.get("id") or uuid.uuid4()),
                "type": wp_type,
            }
            if "data" in wp:
                action_entry["data"] = wp["data"]
            ui_actions.append(action_entry)

    final_spawn = (
        [float(v) for v in spawn_location]
        if spawn_location is not None
        else existing_plan.get("spawnLocation", [0.0, 0.0, 0.0])
    )

    new_plan = {
        "spawnLocation": final_spawn,
        "sequences": [
            {
                "id": str(uuid.uuid4()),
                "type": "route",
                "targetSpeed": float(target_speed),
                "actions": ui_actions,
            }
        ],
    }

    new_mission = {
        **existing_mission,
        "world": world or existing_mission.get("world", "default"),
        "vehicle": vehicle or existing_mission.get("vehicle", "x500_livox_mid_360"),
        "end": {
            "id": existing_mission.get("end", {}).get("id", str(uuid.uuid4())),
            "type": end_action,
        },
        "codeMode": False,
        "takeoffAltitude": float(takeoff_altitude),
        "targetSpeed": float(target_speed),
        "safetyOption": safety_option,
    }

    plan_file.write_text(json.dumps(new_plan, indent=2), encoding="utf-8")
    mission_file.write_text(json.dumps(new_mission, indent=2), encoding="utf-8")

    return {
        "project_id": prj_id,
        "mission_id": mis_id,
        "plan_file": str(plan_file),
        "mission_file": str(mission_file),
        "actions_written": len(ui_actions),
        "spawn_location": final_spawn,
        "plan": new_plan,
        "mission": new_mission,
    }


def write_python_script(
    python_code: str,
    mission_id: Optional[str] = None,
    switch_to_code_mode: bool = True,
    client_data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Save python_code to script.py in the target mission directory and optionally set codeMode=True."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id, client_data_dir)
    script_file = mis_dir / "script.py"
    mission_file = mis_dir / "mission.json"

    script_file.write_text(python_code, encoding="utf-8")

    if switch_to_code_mode and mission_file.exists():
        try:
            mission_data = json.loads(mission_file.read_text(encoding="utf-8"))
            mission_data["codeMode"] = True
            mission_file.write_text(json.dumps(mission_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {
        "project_id": prj_id,
        "mission_id": mis_id,
        "script_file": str(script_file),
        "bytes_written": len(python_code.encode("utf-8")),
        "code_mode": switch_to_code_mode,
    }
