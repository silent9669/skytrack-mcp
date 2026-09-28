"""Static pre-flight validation rules for SkyTrack missions."""

from __future__ import annotations

import math
from typing import Any, List

from skytrack_mcp.autonomy_sdk import validate_uav_python_code
from skytrack_mcp.mission.models import (
    CanonicalMission,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

# Vehicle capability map derived from SkyTrack app.asar renderer database
VEHICLE_CAPABILITIES = {
    "x500_livox_mid_360": {
        "tag": ["LiDAR"],
        "max_balls": 0,
        "has_camera": False,
        "has_spray": False,
    },
    "x500_tennis_balls_no_cam": {
        "tag": ["Firefighting balls"],
        "max_balls": 5,
        "has_camera": False,
        "has_spray": False,
    },
    "x500_tennis_balls": {
        "tag": ["Firefighting balls", "Camera"],
        "max_balls": 5,
        "has_camera": True,
        "has_spray": False,
    },
    "x500_gimbal": {
        "tag": ["Camera"],
        "max_balls": 0,
        "has_camera": True,
        "has_spray": False,
    },
    "x500_mono_cam": {
        "tag": ["Camera"],
        "max_balls": 0,
        "has_camera": True,
        "has_spray": False,
    },
    "x500_spray": {
        "tag": ["Nozzle System", "Camera"],
        "max_balls": 0,
        "has_camera": True,
        "has_spray": True,
    },
    "x500_depth_camera_D435": {
        "tag": ["Camera"],
        "max_balls": 0,
        "has_camera": True,
        "has_spray": False,
    },
    "x500_thermal_camera": {
        "tag": ["Camera"],
        "max_balls": 0,
        "has_camera": True,
        "has_spray": False,
    },
}


def validate_canonical_mission(mission: CanonicalMission) -> ValidationResult:
    """Run full static pre-flight validation against CanonicalMission."""
    issues: List[ValidationIssue] = []

    # 1. Waypoint count or code script
    code_readiness = None
    if mission.code_mode:
        if not mission.python_script or not mission.python_script.strip():
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="EMPTY_CODE_SCRIPT",
                    message="Code Mode mission does not contain a Python script.",
                    fix_suggestion="Add a non-empty Python autonomy script.",
                )
            )
        else:
            code_readiness = validate_uav_python_code(mission.python_script)
            if not code_readiness["static_valid"]:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="INVALID_CODE_SCRIPT",
                        message="Python mission failed static validation: "
                        + "; ".join(code_readiness["errors"]),
                        fix_suggestion="Fix the Python syntax or static validation errors.",
                    )
                )
            elif not code_readiness["execution_ready"]:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="CODE_NOT_EXECUTION_READY",
                        message="Python mission is not execution-ready: "
                        + "; ".join(code_readiness["readiness_issues"]),
                        fix_suggestion="Resolve the code readiness issues before using this mission.",
                    )
                )
    elif not mission.waypoints and not mission.raw_actions:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="EMPTY_MISSION",
                message="Mission contains no waypoints or actions.",
                fix_suggestion="Add at least one navigate waypoint.",
            )
        )
        return ValidationResult(valid=False, issues=issues)

    # 2. Takeoff altitude
    if not (1.0 <= mission.takeoff_altitude <= 50.0):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_TAKEOFF_ALTITUDE",
                message=f"Takeoff altitude {mission.takeoff_altitude}m is outside safe limits [1.0m .. 50.0m].",
                fix_suggestion="Set takeoff altitude between 1.5m and 10.0m.",
            )
        )

    # 3. Target speed
    if not (0.5 <= mission.target_speed <= 12.0):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_TARGET_SPEED",
                message=f"Target speed {mission.target_speed}m/s is outside safe limits [0.5m/s .. 12.0m/s].",
                fix_suggestion="Set target speed between 1.0m/s and 5.0m/s.",
            )
        )

    # 4. Vehicle capabilities check
    v_info = VEHICLE_CAPABILITIES.get(mission.vehicle, {})
    drop_ball_count = 0
    camera_actions_count = 0
    spray_actions_count = 0
    recording_active = False

    for idx, wp in enumerate(mission.waypoints):
        # Altitude check
        if wp.z < 0.5:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="ALTITUDE_TOO_LOW",
                    message=f"Waypoint #{idx+1} altitude {wp.z:.2f}m is too close to ground (< 0.5m).",
                    action_index=idx,
                    action_id=wp.id,
                    fix_suggestion="Raise waypoint altitude to at least 1.5m.",
                )
            )
        elif wp.z > 50.0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="ALTITUDE_TOO_HIGH",
                    message=f"Waypoint #{idx+1} altitude {wp.z:.2f}m exceeds maximum ceiling of 50.0m.",
                    action_index=idx,
                    action_id=wp.id,
                    fix_suggestion="Lower waypoint altitude to below 50.0m.",
                )
            )

        # Check consecutive duplicates
        if idx > 0:
            prev = mission.waypoints[idx - 1]
            dist = math.sqrt((wp.x - prev.x) ** 2 + (wp.y - prev.y) ** 2 + (wp.z - prev.z) ** 2)
            if dist < 0.05 and not wp.after_action and not prev.after_action:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="DUPLICATE_WAYPOINT",
                        message=f"Waypoint #{idx+1} is identical to waypoint #{idx} with no payload action.",
                        action_index=idx,
                        action_id=wp.id,
                        fix_suggestion="Remove redundant consecutive waypoint.",
                    )
                )

        # Payload & Camera tracking
        if wp.after_action == "drop-ball":
            drop_ball_count += 1
            if v_info and v_info.get("max_balls", 0) <= 0:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="UNSUPPORTED_PAYLOAD_ACTION",
                        message=f"Vehicle '{mission.vehicle}' has no ball dropper capability.",
                        action_index=idx,
                        action_id=wp.id,
                        fix_suggestion="Switch vehicle to 'x500_tennis_balls' or 'x500_tennis_balls_no_cam'.",
                    )
                )
        elif wp.after_action in ("take-snapshot", "start-recording-video", "stop-recording-video"):
            camera_actions_count += 1
            if v_info and not v_info.get("has_camera", False):
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="UNSUPPORTED_CAMERA_ACTION",
                        message=f"Vehicle '{mission.vehicle}' has no camera for action '{wp.after_action}'.",
                        action_index=idx,
                        action_id=wp.id,
                        fix_suggestion="Switch vehicle to a camera-equipped model like 'x500_mono_cam'.",
                    )
                )

        if wp.after_action == "start-recording-video":
            if recording_active:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="NESTED_RECORDING",
                        message="Starting video recording while already recording.",
                        action_index=idx,
                        action_id=wp.id,
                    )
                )
            recording_active = True
        elif wp.after_action == "stop-recording-video":
            recording_active = False

    if recording_active:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="UNSTOPPED_RECORDING",
                message="Video recording started but never stopped before mission end.",
                fix_suggestion="Add a 'stop-recording-video' action on the final waypoint.",
            )
        )

    # Ball capacity check
    max_balls = v_info.get("max_balls", 5) if v_info else 5
    if drop_ball_count > max_balls:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="PAYLOAD_CAPACITY_EXCEEDED",
                message=f"Mission drops {drop_ball_count} balls, but vehicle '{mission.vehicle}' only holds {max_balls}.",
                fix_suggestion=f"Reduce drop actions to at most {max_balls}.",
            )
        )

    has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
    stats = {
        "waypoint_count": len(mission.waypoints),
        "drop_ball_actions": drop_ball_count,
        "camera_actions": camera_actions_count,
        "total_distance_m": _compute_total_distance(mission.waypoints),
        "estimated_duration_s": round(
            _compute_total_distance(mission.waypoints) / max(0.5, mission.target_speed), 1
        ),
    }
    if mission.code_mode:
        stats["code_readiness"] = (
            {
                "syntax_valid": False,
                "static_valid": False,
                "sdk_reference_alignment": "UNKNOWN",
                "installed_sdk_compatibility": "UNKNOWN",
                "execution_ready": False,
                "readiness_issues": ["Code Mode mission does not contain a Python script."],
            }
            if code_readiness is None
            else {
                key: code_readiness[key]
                for key in (
                    "syntax_valid",
                    "static_valid",
                    "sdk_reference_alignment",
                    "installed_sdk_compatibility",
                    "execution_ready",
                    "readiness_issues",
                )
            }
        )

    return ValidationResult(
        valid=not has_errors,
        issues=issues,
        stats=stats,
    )


def _compute_total_distance(waypoints: List[Any]) -> float:
    dist = 0.0
    for idx in range(len(waypoints) - 1):
        p0 = waypoints[idx]
        p1 = waypoints[idx + 1]
        dist += math.sqrt((p1.x - p0.x) ** 2 + (p1.y - p0.y) ** 2 + (p1.z - p0.z) ** 2)
    return round(dist, 2)
