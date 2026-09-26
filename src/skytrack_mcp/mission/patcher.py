"""Atomic, snapshot-backed mission patch operations."""

from __future__ import annotations

import datetime
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode
from skytrack_mcp.mission.models import CanonicalMission, Waypoint
from skytrack_mcp.mission.parser import canonical_to_ui_dicts, parse_ui_mission


class MissionPatcher:
    """Manages transactional modifications to SkyTrack mission files with snapshot/rollback support."""

    def __init__(self, mission_dir: Path) -> None:
        self.mission_dir = Path(mission_dir)
        self.mission_file = self.mission_dir / "mission.json"
        self.plan_file = self.mission_dir / "plan.json"
        self.script_file = self.mission_dir / "script.py"
        self.backup_dir = self.mission_dir / "backups"

    def load_canonical(self) -> CanonicalMission:
        if not self.mission_dir.exists():
            raise SkyTrackError(
                SkyTrackErrorCode.MISSION_NOT_FOUND,
                f"Mission directory does not exist: {self.mission_dir}",
            )
        mission_dict = (
            json.loads(self.mission_file.read_text(encoding="utf-8"))
            if self.mission_file.exists()
            else {}
        )
        plan_dict = (
            json.loads(self.plan_file.read_text(encoding="utf-8"))
            if self.plan_file.exists()
            else {}
        )
        script_text = (
            self.script_file.read_text(encoding="utf-8")
            if self.script_file.exists()
            else ""
        )

        project_id = self.mission_dir.parent.name.removeprefix("prj-")
        mission_id = self.mission_dir.name.removeprefix("mis-")

        return parse_ui_mission(
            project_id=project_id,
            mission_id=mission_id,
            mission_dict=mission_dict,
            plan_dict=plan_dict,
            script_text=script_text,
        )

    def create_snapshot(self) -> str:
        """Create a recoverable snapshot backup of current mission files."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        snap_folder = self.backup_dir / ts
        snap_folder.mkdir(parents=True, exist_ok=True)

        for src in (self.mission_file, self.plan_file, self.script_file):
            if src.exists():
                shutil.copy2(src, snap_folder / src.name)
        return ts

    def rollback_to_snapshot(self, snapshot_id: str) -> None:
        """Restore mission files from a previous snapshot backup."""
        snap_folder = self.backup_dir / snapshot_id
        if not snap_folder.exists():
            raise SkyTrackError(
                SkyTrackErrorCode.MISSION_NOT_FOUND,
                f"Snapshot '{snapshot_id}' does not exist in {self.backup_dir}",
            )
        for name in ("mission.json", "plan.json", "script.py"):
            snap_file = snap_folder / name
            dst = self.mission_dir / name
            if snap_file.exists():
                shutil.copy2(snap_file, dst)
            elif dst.exists():
                dst.unlink()

    def save_canonical(self, mission: CanonicalMission, preserve_snapshot: bool = True) -> str:
        """Serialize and atomically write CanonicalMission back to plan.json and mission.json."""
        snap_id = self.create_snapshot() if preserve_snapshot else ""
        plan_dict, mission_dict = canonical_to_ui_dicts(mission)

        self.plan_file.write_text(json.dumps(plan_dict, indent=2), encoding="utf-8")
        self.mission_file.write_text(json.dumps(mission_dict, indent=2), encoding="utf-8")

        if mission.python_script is not None:
            self.script_file.write_text(mission.python_script, encoding="utf-8")

        return snap_id

    def patch_mission(self, patches: Dict[str, Any]) -> Tuple[CanonicalMission, str]:
        """Apply patch-style operations to the mission and save."""
        mission = self.load_canonical()
        snap_id = self.create_snapshot()

        # Update metadata if provided
        if "world" in patches:
            mission.world = str(patches["world"])
        if "vehicle" in patches:
            mission.vehicle = str(patches["vehicle"])
        if "target_speed" in patches:
            mission.target_speed = float(patches["target_speed"])
        if "takeoff_altitude" in patches:
            mission.takeoff_altitude = float(patches["takeoff_altitude"])
        if "safety_option" in patches:
            mission.safety_option = patches["safety_option"]
        if "end_action" in patches:
            mission.end_action = patches["end_action"]
        if "code_mode" in patches:
            mission.code_mode = bool(patches["code_mode"])

        # Patch waypoints
        if "add_waypoints" in patches:
            for wp_item in patches["add_waypoints"]:
                wp = Waypoint(
                    id=str(wp_item.get("id") or uuid.uuid4()),
                    x=float(wp_item["x"]),
                    y=float(wp_item["y"]),
                    z=float(wp_item.get("z", mission.takeoff_altitude)),
                    after_action=wp_item.get("after_action"),
                    target_speed=wp_item.get("target_speed"),
                )
                mission.waypoints.append(wp)

        if "set_waypoints" in patches:
            new_wps = []
            for wp_item in patches["set_waypoints"]:
                new_wps.append(
                    Waypoint(
                        id=str(wp_item.get("id") or uuid.uuid4()),
                        x=float(wp_item["x"]),
                        y=float(wp_item["y"]),
                        z=float(wp_item.get("z", mission.takeoff_altitude)),
                        after_action=wp_item.get("after_action"),
                        target_speed=wp_item.get("target_speed"),
                    )
                )
            mission.waypoints = new_wps

        if "remove_waypoint_ids" in patches:
            rem_ids = set(patches["remove_waypoint_ids"])
            mission.waypoints = [wp for wp in mission.waypoints if wp.id not in rem_ids]

        self.save_canonical(mission, preserve_snapshot=False)
        return mission, snap_id
