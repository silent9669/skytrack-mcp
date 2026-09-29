"""Requirement-by-requirement verification matrix evaluator."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RequirementVerificationItem(BaseModel):
    requirement_name: str
    mandatory: bool = True
    expected: str
    observed: str
    evidence: str
    status: VerificationStatus
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    notes: Optional[str] = None


class MissionVerificationMatrix(BaseModel):
    mission_id: str
    overall_status: VerificationStatus
    items: List[RequirementVerificationItem] = Field(default_factory=list)
    summary: str


def evaluate_mission_requirements(
    mission_id: str,
    requirements: List[Dict[str, Any]],
    report_data: Dict[str, Any],
) -> MissionVerificationMatrix:
    """Evaluate assignment requirements against authentic flight report and telemetry evidence."""
    items: List[RequirementVerificationItem] = []
    all_mandatory_pass = True

    telem = report_data.get("telemetry_state", {})
    media = report_data.get("media_output", {})
    exec_status = report_data.get("execution_status", "UNKNOWN")
    has_native_report = report_data.get("report_provenance") == "authentic"

    for req in requirements:
        name = req.get("name", "Unnamed Requirement")
        mandatory = bool(req.get("mandatory", True))
        req_type = req.get("type", "")

        status = VerificationStatus.UNKNOWN
        observed_str = "Not observed"
        evidence_str = ""

        # 1. Landed Safely Check
        if req_type == "landed_safely":
            landed = telem.get("landed_state")
            if has_native_report and exec_status in ("COMPLETED", "Succeeded") and report_data.get("landing_completed") is True:
                status = VerificationStatus.PASS
                observed_str = "Native execution report confirms completed landing"
                evidence_str = "report_provenance == 'authentic', landing_completed == True"
            elif telem.get("connected") and landed in ("IN_AIR", "TAKEOFF", "LANDING"):
                status = VerificationStatus.FAIL
                observed_str = f"Drone still airborne in state '{landed}'"
                evidence_str = f"telemetry.landed_state == '{landed}'"
            else:
                status = VerificationStatus.UNKNOWN
                observed_str = "Completed landing not observed in native report"
                evidence_str = "No native completed RTL/LAND event"

        # 2. Takeoff Altitude Check (Numerical!)
        elif req_type == "takeoff_altitude":
            expected_alt = float(req.get("expected", 1.5))
            actual_alt = report_data.get("observed_takeoff_altitude_m") if has_native_report else None
            if actual_alt is None:
                observed_str = "Takeoff altitude not observed in native report"
                evidence_str = "Native TAKEOFF target_altitude unavailable"
            else:
                actual_alt = float(actual_alt)
                observed_str = f"Reported takeoff target altitude is {actual_alt:.2f}m"
                evidence_str = f"native TAKEOFF target_altitude == {actual_alt} (expected >= {expected_alt})"
                status = VerificationStatus.PASS if actual_alt >= expected_alt - 1e-6 else VerificationStatus.FAIL

        # 3. Waypoints Reached / Defined Check
        elif req_type in ("min_waypoints", "waypoints_reached"):
            min_count = int(req.get("expected", 1))
            reached_count = int(report_data.get("waypoints_reached_count", 0))
            observed_str = f"{reached_count} waypoints reached during flight"
            evidence_str = f"waypoints_reached_count == {reached_count} (expected >= {min_count})"
            if has_native_report:
                status = VerificationStatus.PASS if reached_count >= min_count else VerificationStatus.FAIL
            else:
                status = VerificationStatus.UNKNOWN
                evidence_str = "No native execution report for waypoint arrivals"

        # 4. Target World Verification
        elif req_type == "world":
            expected_world = str(req.get("expected", "default"))
            actual_world = str(report_data.get("world", ""))
            observed_str = f"World is '{actual_world}'"
            evidence_str = f"report_data.world == '{actual_world}'"
            if has_native_report:
                status = VerificationStatus.PASS if actual_world.lower() == expected_world.lower() else VerificationStatus.FAIL
            else:
                evidence_str = "No native execution report for world verification"

        # 5. Collision Freedom Check
        elif req_type == "collision_freedom":
            is_free = req.get("is_collision_free")
            conflicts = req.get("conflicts")
            if is_free is True and conflicts == [] and req.get("geometry_complete") is True:
                status = VerificationStatus.PASS
                observed_str = "Parsed geometry shows no route collisions"
                evidence_str = "check_route_collisions: geometry_complete == True, conflicts == []"
            elif conflicts or is_free is False and req.get("geometry_complete") is True:
                status = VerificationStatus.FAIL
                observed_str = f"Route has {len(conflicts or [])} collision conflicts"
                evidence_str = f"conflicts == {conflicts}"
            else:
                observed_str = "Collision geometry or check result unavailable"
                evidence_str = "geometry_complete and explicit collision result required"

        # 6. Defect Detection Check
        elif req_type == "defect_detected":
            issues = req.get("detected_issues", [])
            if len(issues) > 0:
                status = VerificationStatus.PASS
                observed_str = f"{len(issues)} static defects correctly caught by validator"
                evidence_str = f"validator.issues == {[i.get('code') for i in issues]}"
            else:
                status = VerificationStatus.FAIL
                observed_str = "No defects detected in bad mission"
                evidence_str = "validator.valid == True (expected False)"

        # 7. Recovery Actions Check
        elif req_type == "recovery_actions":
            min_actions = int(req.get("expected", 1))
            actions_list = req.get("actions_taken", [])
            actual_count = len(actions_list)
            observed_str = f"{actual_count} recovery actions executed"
            evidence_str = f"recovery.actions_taken == {actions_list}"
            status = VerificationStatus.PASS if actual_count >= min_actions else VerificationStatus.FAIL

        # 8. Sensor Image Captures Check
        elif req_type == "captures":
            min_caps = int(req.get("expected", 1))
            actual_caps = int(media.get("captures_count", 0))
            observed_str = f"{actual_caps} images captured"
            evidence_str = f"media.captures_count == {actual_caps}"
            status = VerificationStatus.PASS if actual_caps >= min_caps else VerificationStatus.FAIL

        # 9. Payload Triggers Check
        elif req_type == "payload_drops":
            min_drops = int(req.get("expected", 1))
            actual_drops = int(report_data.get("payload_triggers_count", 0))
            observed_str = f"{actual_drops} payload drops executed"
            evidence_str = f"payload_triggers_count == {actual_drops}"
            status = VerificationStatus.PASS if actual_drops >= min_drops else VerificationStatus.FAIL

        # 10. Battery Safety Margin Check
        elif req_type == "battery_margin":
            min_battery = float(req.get("expected", 20.0))
            actual_bat = telem.get("battery_percentage")
            if actual_bat is not None:
                observed_str = f"Remaining battery: {actual_bat}%"
                evidence_str = f"telemetry.battery_percentage == {actual_bat}"
                status = VerificationStatus.PASS if actual_bat >= min_battery else VerificationStatus.FAIL
            else:
                status = VerificationStatus.UNKNOWN
                observed_str = "Battery telemetry unavailable"
                evidence_str = "battery_percentage is null"

        else:
            status = VerificationStatus.UNKNOWN
            observed_str = "Custom rule not directly measurable by automated heuristics"
            evidence_str = "Manual / visual inspection required"

        if mandatory and status != VerificationStatus.PASS:
            all_mandatory_pass = False

        items.append(
            RequirementVerificationItem(
                requirement_name=name,
                mandatory=mandatory,
                expected=str(req.get("expected", "True")),
                observed=observed_str,
                evidence=evidence_str,
                status=status,
                confidence="HIGH" if status != VerificationStatus.UNKNOWN else "LOW",
            )
        )

    overall = VerificationStatus.PASS if all_mandatory_pass and items else VerificationStatus.FAIL
    summary = (
        f"Verification {overall.value}: {sum(1 for i in items if i.status == VerificationStatus.PASS)}/{len(items)} "
        "requirements verified successfully."
    )

    return MissionVerificationMatrix(
        mission_id=mission_id,
        overall_status=overall,
        items=items,
        summary=summary,
    )
