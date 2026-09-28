from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from skytrack_mcp.clients import storage_sync
from skytrack_mcp.clients.storage_sync import (
    commit_mission_files,
    switch_mission_mode,
    write_python_script,
    write_visual_route,
)


def make_mission(tmp_path: Path, *, script: str = "print('kept')\n") -> tuple[Path, dict[str, Any], dict[str, Any]]:
    mission_dir = tmp_path / "prj-project-1" / "mis-mission-1"
    mission_dir.mkdir(parents=True)
    mission = {
        "name": "Existing",
        "world": "warehouse",
        "vehicle": "x500",
        "codeMode": False,
        "missionExtension": {"keep": True},
    }
    plan = {
        "spawnLocation": [0, 0, 0],
        "sequences": [{"id": "route-id", "type": "route", "actions": []}],
        "planExtension": "keep",
    }
    (mission_dir / "mission.json").write_text(json.dumps(mission), encoding="utf-8")
    (mission_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    if script is not None:
        (mission_dir / "script.py").write_text(script, encoding="utf-8")
    return mission_dir, mission, plan


def test_commit_mission_files_writes_and_verifies_exact_bytes(tmp_path: Path) -> None:
    updates = {"mission.json": '{"codeMode": true}', "script.py": "print('saved')\n"}

    hashes = commit_mission_files(tmp_path, updates)

    for name, text in updates.items():
        content = (tmp_path / name).read_bytes()
        assert content == text.encode("utf-8")
        assert hashes[name] == hashlib.sha256(content).hexdigest()


def test_commit_mission_files_rejects_unapproved_filename(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported mission filenames"):
        commit_mission_files(tmp_path, {"private.txt": "no"})
    assert list(tmp_path.iterdir()) == []


def test_commit_mission_files_rolls_back_after_atomic_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "plan.json").write_bytes(b"old plan")
    (tmp_path / "mission.json").write_bytes(b"old mission")
    original_replace = os.replace
    failed_once = False

    def fail_second_replace(source: Any, destination: Any) -> None:
        nonlocal failed_once
        if Path(destination).name == "mission.json" and not failed_once:
            failed_once = True
            raise OSError("simulated replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(storage_sync.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        commit_mission_files(tmp_path, {"plan.json": "new plan", "mission.json": "new mission"})

    assert (tmp_path / "plan.json").read_bytes() == b"old plan"
    assert (tmp_path / "mission.json").read_bytes() == b"old mission"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["mission.json", "plan.json"]


def test_commit_mission_files_rolls_back_after_readback_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "plan.json").write_bytes(b"old plan")
    (tmp_path / "mission.json").write_bytes(b"old mission")
    original_read_bytes = Path.read_bytes
    plan_reads = 0

    def mismatch_during_verification(path: Path) -> bytes:
        nonlocal plan_reads
        result = original_read_bytes(path)
        if path.name == "plan.json":
            plan_reads += 1
            if plan_reads == 2:
                return b"mismatch"
        return result

    monkeypatch.setattr(Path, "read_bytes", mismatch_during_verification)

    with pytest.raises(OSError, match="Read-back verification failed"):
        commit_mission_files(tmp_path, {"plan.json": "new plan", "mission.json": "new mission"})

    assert original_read_bytes(tmp_path / "plan.json") == b"old plan"
    assert original_read_bytes(tmp_path / "mission.json") == b"old mission"


def test_route_and_script_writes_keep_other_representation_and_return_hashes(tmp_path: Path) -> None:
    mission_dir, original_mission, _ = make_mission(tmp_path)
    original_script = (mission_dir / "script.py").read_bytes()

    route_result = write_visual_route(
        [{"x": 1, "y": 2, "z": 3}],
        mission_id="mission-1",
        project_id="project-1",
        client_data_dir=tmp_path,
    )
    assert (mission_dir / "script.py").read_bytes() == original_script
    assert route_result["persistence"] == "SAVED_AND_READ_BACK"
    assert route_result["sha256"]["plan.json"] == hashlib.sha256(
        (mission_dir / "plan.json").read_bytes()
    ).hexdigest()
    saved_mission = json.loads((mission_dir / "mission.json").read_text(encoding="utf-8"))
    assert saved_mission["missionExtension"] == original_mission["missionExtension"]

    original_plan = (mission_dir / "plan.json").read_bytes()
    script_result = write_python_script(
        "print('new script')\n",
        mission_id="mission-1",
        project_id="project-1",
        client_data_dir=tmp_path,
    )
    assert (mission_dir / "plan.json").read_bytes() == original_plan
    assert script_result["persistence"] == "SAVED_AND_READ_BACK"
    assert script_result["sha256"]["script.py"] == hashlib.sha256(
        (mission_dir / "script.py").read_bytes()
    ).hexdigest()
    saved_mission = json.loads((mission_dir / "mission.json").read_text(encoding="utf-8"))
    assert saved_mission["codeMode"] is True
    assert saved_mission["missionExtension"] == original_mission["missionExtension"]


def test_python_script_write_without_mode_switch_leaves_metadata_unchanged(tmp_path: Path) -> None:
    mission_dir, mission, _ = make_mission(tmp_path)
    original_mission = (mission_dir / "mission.json").read_bytes()
    original_plan = (mission_dir / "plan.json").read_bytes()

    result = write_python_script(
        "print('script only')",
        mission_id="mission-1",
        project_id="project-1",
        switch_to_code_mode=False,
        client_data_dir=tmp_path,
    )

    assert (mission_dir / "mission.json").read_bytes() == original_mission
    assert (mission_dir / "plan.json").read_bytes() == original_plan
    assert result["code_mode"] is False
    assert set(result["sha256"]) == {"script.py"}
    assert mission["codeMode"] is False


def test_write_script_does_not_swallow_mission_metadata_errors(tmp_path: Path) -> None:
    mission_dir, _, _ = make_mission(tmp_path)
    (mission_dir / "mission.json").write_text("not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        write_python_script(
            "print('must not persist')",
            mission_id="mission-1",
            project_id="project-1",
            client_data_dir=tmp_path,
        )

    assert (mission_dir / "script.py").read_text(encoding="utf-8") == "print('kept')\n"


def test_switch_mode_preserves_both_representations_and_returns_refresh_instructions(
    tmp_path: Path,
) -> None:
    mission_dir, _, _ = make_mission(tmp_path)
    plan_before = (mission_dir / "plan.json").read_bytes()
    script_before = (mission_dir / "script.py").read_bytes()

    result = switch_mission_mode(
        "mission-1", "project-1", True, client_data_dir=tmp_path
    )

    assert json.loads((mission_dir / "mission.json").read_text(encoding="utf-8"))["codeMode"] is True
    assert (mission_dir / "plan.json").read_bytes() == plan_before
    assert (mission_dir / "script.py").read_bytes() == script_before
    assert result["persistence"] == "SAVED_AND_READ_BACK"
    assert result["sha256"]["plan.json"] == hashlib.sha256(plan_before).hexdigest()
    assert result["sha256"]["script.py"] == hashlib.sha256(script_before).hexdigest()
    assert result["refresh_instructions"]["active_representation"] == "script.py"
    assert result["refresh_instructions"]["reload_mission"] is True


def test_switch_mode_requires_existing_nonempty_target_representation(tmp_path: Path) -> None:
    mission_dir, _, _ = make_mission(tmp_path, script="")
    with pytest.raises(ValueError, match="script.py is missing or empty"):
        switch_mission_mode("mission-1", "project-1", True, client_data_dir=tmp_path)

    (mission_dir / "script.py").write_text("print('ok')", encoding="utf-8")
    (mission_dir / "plan.json").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="plan.json is missing or empty"):
        switch_mission_mode("mission-1", "project-1", False, client_data_dir=tmp_path)
