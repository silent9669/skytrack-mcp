from __future__ import annotations

import ast

from skytrack_mcp.autonomy_sdk import (
    AUTONOMY_LEVEL_TEMPLATES,
    SDK_REFERENCE_COMMIT,
    get_uav_python_sdk_reference_data,
    validate_uav_python_code,
)
from skytrack_mcp.mission.models import CanonicalMission
from skytrack_mcp.mission.validator import validate_canonical_mission

READY_CODE = '''
from local_planner import boot_drone, takeoff, land

def scenario(ctx):
    yield takeoff(alt_m=3.0)
    yield land()

def main():
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()
'''


def test_reference_data_uses_the_pinned_sdk_commit() -> None:
    reference = get_uav_python_sdk_reference_data()

    assert SDK_REFERENCE_COMMIT == "bb0f5ba611c59cd68d32d1fe04b40765836a1b33"
    assert reference["reference_commit"] == SDK_REFERENCE_COMMIT


def test_readiness_marks_a_valid_pinned_sdk_script_execution_ready() -> None:
    result = validate_uav_python_code(READY_CODE)

    assert result["valid"] is True
    assert result["syntax_valid"] is True
    assert result["static_valid"] is True
    assert result["sdk_reference_alignment"] == "REFERENCE_MATCH"
    assert result["installed_sdk_compatibility"] == "UNKNOWN"
    assert result["execution_ready"] is True
    assert result["readiness_issues"] == []


def test_readiness_rejects_detector_and_sprayer_imports_from_local_planner() -> None:
    code = READY_CODE.replace(
        "from local_planner import boot_drone, takeoff, land",
        "from local_planner import boot_drone, takeoff, land, Detector, Sprayer",
    )
    result = validate_uav_python_code(code)

    assert result["sdk_reference_alignment"] == "INCOMPATIBLE"
    assert result["sdk_compatibility"] == "INCOMPATIBLE"
    assert result["execution_ready"] is False
    assert any("skytrack_autonomy" in issue for issue in result["readiness_issues"])


def test_invalid_syntax_has_readiness_fields_without_losing_legacy_fields() -> None:
    result = validate_uav_python_code("def scenario(:\n    pass\n")

    assert result["valid"] is False
    assert result["detected_level"] == 0
    assert result["syntax_valid"] is False
    assert result["static_valid"] is False
    assert result["sdk_reference_alignment"] == "UNKNOWN"
    assert result["installed_sdk_compatibility"] == "UNKNOWN"
    assert result["execution_ready"] is False
    assert result["readiness_issues"]
    assert "used_steps" in result
    assert "custom_components" in result


def test_level_4_template_registers_and_uses_canonical_detection_and_spray_services() -> (
    None
):
    code = AUTONOMY_LEVEL_TEMPLATES[4]["code"]
    tree = ast.parse(code)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "skytrack_autonomy"
        for alias in node.names
    }
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    model_name_configured = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "MODEL_NAME"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value == "det-h2026-v26n-b-fp32-640"
        for node in ast.walk(tree)
    )
    detector_registration = any(
        isinstance(call.func, ast.Name)
        and call.func.id == "Detector"
        and any(
            keyword.arg == "model_name"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "det-h2026-v26n-b-fp32-640"
            for keyword in call.keywords
        )
        and any(
            keyword.arg == "classes"
            and isinstance(keyword.value, (ast.List, ast.Tuple))
            and [
                elt.value
                for elt in keyword.value.elts
                if isinstance(elt, ast.Constant)
            ]
            == ["stressed"]
            for keyword in call.keywords
        )
        for call in calls
    )
    detector_request = any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "request"
        for call in calls
    )
    bounded_wait = any(
        isinstance(call.func, ast.Name)
        and call.func.id == "SkillStep"
        and any(keyword.arg == "is_done" for keyword in call.keywords)
        for call in calls
    )

    assert {"Detector", "Sprayer"} <= imports
    assert model_name_configured
    assert detector_registration
    assert detector_request
    assert bounded_wait
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "Sprayer"
        for call in calls
    )
    assert any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "on"
        for call in calls
    )
    assert any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "off"
        for call in calls
    )
    readiness = validate_uav_python_code(code)
    assert readiness["execution_ready"] is True
    assert {"Detector", "Sprayer"} <= set(readiness["used_services"])


def test_code_mode_accepts_a_nonempty_script_without_visual_waypoints() -> None:
    mission = CanonicalMission(
        project_id="project-1",
        mission_id="mission-1",
        code_mode=True,
        python_script=READY_CODE,
    )

    result = validate_canonical_mission(mission)

    assert result.valid is True
    assert not any(issue.code == "EMPTY_MISSION" for issue in result.issues)
    assert result.stats["code_readiness"]["execution_ready"] is True
    assert result.stats["code_readiness"]["sdk_reference_alignment"] == "REFERENCE_MATCH"


def test_code_mode_reports_an_error_for_an_empty_script() -> None:
    mission = CanonicalMission(
        project_id="project-1",
        mission_id="mission-1",
        code_mode=True,
        python_script="  ",
    )

    result = validate_canonical_mission(mission)

    assert result.valid is False
    assert any(issue.code == "EMPTY_CODE_SCRIPT" for issue in result.issues)
    assert not any(issue.code == "EMPTY_MISSION" for issue in result.issues)
