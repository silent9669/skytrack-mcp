"""Synchronizes missions, visual routes (plan.json), metadata (mission.json), and scripts (script.py)
with the local SkyTrack Electron application storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from skytrack_mcp.config import CLIENT_DATA_DIR

_ALLOWED_MISSION_FILES = {"mission.json", "plan.json", "script.py"}


def commit_mission_files(mission_dir: Path, updates: dict[str, str]) -> dict[str, str]:
    """Atomically replace allowed mission files, verifying each write before commit."""
    mission_dir = Path(mission_dir)
    invalid = set(updates) - _ALLOWED_MISSION_FILES
    if invalid:
        raise ValueError(f"Unsupported mission filenames: {sorted(invalid)}")

    contents = {name: text.encode("utf-8") for name, text in updates.items()}
    snapshots = {
        name: (mission_dir / name).read_bytes() if (mission_dir / name).exists() else None
        for name in contents
    }
    temporary_files: dict[str, Path] = {}
    replaced_names: list[str] = []
    try:
        for name, content in contents.items():
            fd, temp_path = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=mission_dir)
            temporary = Path(temp_path)
            temporary_files[name] = temporary
            with os.fdopen(fd, "wb") as file_obj:
                file_obj.write(content)
                file_obj.flush()
                os.fsync(file_obj.fileno())

        for name, temporary in temporary_files.items():
            replaced_names.append(name)
            os.replace(temporary, mission_dir / name)

        hashes: dict[str, str] = {}
        for name, expected in contents.items():
            actual = (mission_dir / name).read_bytes()
            if actual != expected:
                raise OSError(f"Read-back verification failed for {name}")
            hashes[name] = hashlib.sha256(actual).hexdigest()
        return hashes
    except Exception as write_error:
        rollback_errors = []
        for name in replaced_names:
            original = snapshots[name]
            destination = mission_dir / name
            rollback_path: Path | None = None
            try:
                if original is None:
                    destination.unlink(missing_ok=True)
                else:
                    fd, temp_path = tempfile.mkstemp(
                        prefix=f".{name}.rollback.", suffix=".tmp", dir=mission_dir
                    )
                    rollback_path = Path(temp_path)
                    with os.fdopen(fd, "wb") as file_obj:
                        file_obj.write(original)
                        file_obj.flush()
                        os.fsync(file_obj.fileno())
                    os.replace(rollback_path, destination)
            except Exception as rollback_error:  # noqa: BLE001 - attempt every rollback operation
                rollback_errors.append(f"{name}: {rollback_error}")
            finally:
                if rollback_path is not None:
                    rollback_path.unlink(missing_ok=True)
        if rollback_errors:
            raise RuntimeError(
                f"Mission file transaction failed and rollback was incomplete: {rollback_errors}"
            ) from write_error
        raise
    finally:
        for temporary in temporary_files.values():
            temporary.unlink(missing_ok=True)


def list_all_missions(client_data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return all missions across all projects in ClientData, sorted by most recently modified."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    missions: list[dict[str, Any]] = []
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

            metadata: dict[str, Any] = {}
            if mission_file.exists():
                try:
                    metadata = json.loads(mission_file.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001 - malformed mission entries are skipped by listing
                    metadata = {}

            plan_data: dict[str, Any] = {}
            if plan_file.exists():
                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001 - malformed plan entries are skipped by listing
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
    mission_id: str | None = None,
    client_data_dir: Path | None = None,
    project_id: str | None = None,
    create_if_missing: bool = False,
) -> tuple[Path, str, str]:
    """Resolve (mission_dir, project_id, mission_id).

    Requires an explicit mission_id; silent fallback to 'most recent' is prohibited.
    Creation requires an explicit project_id; hardcoded project fallbacks are prohibited.
    """
    if not mission_id or not mission_id.strip():
        raise ValueError("Explicit mission_id is required. Inferred or most-recent fallback is prohibited.")

    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    missions = list_all_missions(client_data_dir)

    clean_id = mission_id.removeprefix("mis-").strip()
    clean_prj_id = project_id.removeprefix("prj-").strip() if project_id else None

    matches = [
        m
        for m in missions
        if m["mission_id"] == clean_id
        and (not clean_prj_id or m["project_id"] == clean_prj_id)
    ]
    if len(matches) == 1:
        m = matches[0]
        return Path(m["path"]), m["project_id"], m["mission_id"]
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous mission_id '{clean_id}' exists in multiple projects: "
            f"{[m['project_id'] for m in matches]}. Explicit project_id is required."
        )

    if create_if_missing:
        if not clean_prj_id:
            raise ValueError("Cannot create mission without an explicit project_id. Hardcoded or guessed project fallbacks are prohibited.")

        new_dir = client_data_dir / f"prj-{clean_prj_id}" / f"mis-{clean_id}"
        new_dir.mkdir(parents=True, exist_ok=True)
        if not (new_dir / "mission.json").exists():
            (new_dir / "mission.json").write_text(
                json.dumps({"world": "default", "vehicle": "x500_livox_mid_360", "codeMode": False}, indent=2),
                encoding="utf-8",
            )
        if not (new_dir / "plan.json").exists():
            (new_dir / "plan.json").write_text(
                json.dumps({"spawnLocation": [0, 0, 0], "sequences": []}, indent=2),
                encoding="utf-8",
            )
        return new_dir, clean_prj_id, clean_id

    raise FileNotFoundError(
        f"Mission '{mission_id}' not found. Available: {[m['mission_id'] for m in missions]}"
    )


def read_mission_details(
    mission_id: str | None = None,
    client_data_dir: Path | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Read full mission.json, plan.json, and script.py for a mission."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    mis_dir, prj_id, mis_id = resolve_mission_dir(mission_id, client_data_dir, project_id=project_id)
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
    waypoints: list[dict[str, Any]],
    mission_id: str | None = None,
    spawn_location: list[float] | None = None,
    takeoff_altitude: float = 2.0,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    world: str | None = None,
    vehicle: str | None = None,
    client_data_dir: Path | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Write a visual route into plan.json and update mission.json for the SkyTrack UI."""
    mis_dir, prj_id, mis_id = resolve_mission_dir(
        mission_id, client_data_dir, project_id=project_id, create_if_missing=True
    )
    mission_file = mis_dir / "mission.json"
    plan_file = mis_dir / "plan.json"

    existing_mission: dict[str, Any] = (
        json.loads(mission_file.read_text(encoding="utf-8")) if mission_file.exists() else {}
    )
    existing_plan: dict[str, Any] = (
        json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
    )
    if not isinstance(existing_mission, dict) or not isinstance(existing_plan, dict):
        raise TypeError("Mission metadata and plan files must contain JSON objects")

    ui_actions: list[dict[str, Any]] = []
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
            action_entry: dict[str, Any] = {
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
        **existing_plan,
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

    existing_end = existing_mission.get("end", {})
    if not isinstance(existing_end, dict):
        existing_end = {}
    new_mission = {
        **existing_mission,
        "world": world or existing_mission.get("world", "default"),
        "vehicle": vehicle or existing_mission.get("vehicle", "x500_livox_mid_360"),
        "end": {
            **existing_end,
            "id": existing_end.get("id", str(uuid.uuid4())),
            "type": end_action,
        },
        "codeMode": False,
        "takeoffAltitude": float(takeoff_altitude),
        "targetSpeed": float(target_speed),
        "safetyOption": safety_option,
    }

    hashes = commit_mission_files(
        mis_dir,
        {
            "plan.json": json.dumps(new_plan, indent=2),
            "mission.json": json.dumps(new_mission, indent=2),
        },
    )

    return {
        "project_id": prj_id,
        "mission_id": mis_id,
        "plan_file": str(plan_file),
        "mission_file": str(mission_file),
        "actions_written": len(ui_actions),
        "spawn_location": final_spawn,
        "plan": new_plan,
        "mission": new_mission,
        "persistence": "SAVED_AND_READ_BACK",
        "sha256": hashes,
    }


def write_python_script(
    python_code: str,
    mission_id: str | None = None,
    switch_to_code_mode: bool = True,
    client_data_dir: Path | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Save python_code to script.py in the target mission directory and optionally set codeMode=True."""
    client_data_dir = client_data_dir or CLIENT_DATA_DIR
    mis_dir, prj_id, mis_id = resolve_mission_dir(
        mission_id, client_data_dir, project_id=project_id, create_if_missing=True
    )
    script_file = mis_dir / "script.py"
    mission_file = mis_dir / "mission.json"
    updates = {"script.py": python_code}

    if switch_to_code_mode:
        mission_data = json.loads(mission_file.read_text(encoding="utf-8"))
        if not isinstance(mission_data, dict):
            raise TypeError("mission.json must contain a JSON object")
        mission_data["codeMode"] = True
        updates["mission.json"] = json.dumps(mission_data, indent=2)

    hashes = commit_mission_files(mis_dir, updates)
    return {
        "project_id": prj_id,
        "mission_id": mis_id,
        "script_file": str(script_file),
        "bytes_written": len(python_code.encode("utf-8")),
        "code_mode": switch_to_code_mode,
        "persistence": "SAVED_AND_READ_BACK",
        "sha256": hashes,
    }


def switch_mission_mode(
    mission_id: str,
    project_id: str,
    code_mode: bool,
    client_data_dir: Path | None = None,
) -> dict[str, Any]:
    """Switch active mission representation without changing either stored representation."""
    mission_dir, resolved_project_id, resolved_mission_id = resolve_mission_dir(
        mission_id,
        client_data_dir,
        project_id=project_id,
    )
    mission_file = mission_dir / "mission.json"
    plan_file = mission_dir / "plan.json"
    script_file = mission_dir / "script.py"

    mission_data = json.loads(mission_file.read_text(encoding="utf-8"))
    if not isinstance(mission_data, dict):
        raise TypeError("mission.json must contain a JSON object")
    representations = {
        "plan.json": plan_file.read_bytes() if plan_file.exists() else None,
        "script.py": script_file.read_bytes() if script_file.exists() else None,
    }
    target_name = "script.py" if code_mode else "plan.json"
    target_content = representations[target_name]
    if not target_content:
        raise ValueError(f"Cannot switch mission mode: {target_name} is missing or empty")

    mission_data["codeMode"] = bool(code_mode)
    hashes = commit_mission_files(
        mission_dir,
        {"mission.json": json.dumps(mission_data, indent=2)},
    )
    for name, original in representations.items():
        current = mission_dir / name
        actual = current.read_bytes() if current.exists() else None
        if actual != original:
            raise OSError(f"Representation changed during mode switch: {name}")
        if actual is not None:
            hashes[name] = hashlib.sha256(actual).hexdigest()

    active_file = "script.py" if code_mode else "plan.json"
    return {
        "project_id": resolved_project_id,
        "mission_id": resolved_mission_id,
        "code_mode": bool(code_mode),
        "persistence": "SAVED_AND_READ_BACK",
        "sha256": hashes,
        "refresh_instructions": {
            "reload_mission": True,
            "active_representation": active_file,
            "message": f"Reload the mission and use {active_file} as the active representation.",
        },
    }
