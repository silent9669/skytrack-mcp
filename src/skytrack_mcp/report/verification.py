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
    """Evaluate assignment requirements against harvested flight report data.

    Each requirement dict can specify:
    - name: str
    - mandatory: bool (default True)
    - type: "landed_safely" | "min_waypoints" | "payload_drops" | "captures" | "battery_margin" | "world"
    - expected: Any
    """
    items: List[RequirementVerificationItem] = []
    all_mandatory_pass = True

    telem = report_data.get("telemetry_state", {})
    media = report_data.get("media_output", {})

    for req in requirements:
        name = req.get("name", "Unnamed Requirement")
        mandatory = bool(req.get("mandatory", True))
        req_type = req.get("type", "")

        status = VerificationStatus.UNKNOWN
        observed_str = "Not observed"
        evidence_str = ""

        if req_type == "landed_safely":
            landed = telem.get("landed_state")
            expected_val = "ON_GROUND"
            if landed == "ON_GROUND":
                status = VerificationStatus.PASS
                observed_str = "Drone landed safely on ground"
                evidence_str = f"telemetry.landed_state == '{landed}'"
            elif landed in ("IN_AIR", "TAKEOFF", "LANDING"):
                status = VerificationStatus.FAIL
                observed_str = f"Drone still in state '{landed}'"
                evidence_str = f"telemetry.landed_state == '{landed}'"
            else:
                status = VerificationStatus.UNKNOWN
                observed_str = f"Unknown landed state '{landed}'"
                evidence_str = "telemetry not connected or invalid"

        elif req_type == "min_waypoints":
            min_count = int(req.get("expected", 1))
            actual = int(report_data.get("total_planned_waypoints", 0))
            observed_str = f"{actual} waypoints"
            evidence_str = f"total_planned_waypoints == {actual}"
            status = VerificationStatus.PASS if actual >= min_count else VerificationStatus.FAIL

        elif req_type == "world":
            expected_world = str(req.get("expected", "default"))
            actual_world = str(report_data.get("world", ""))
            observed_str = f"World is '{actual_world}'"
            evidence_str = f"report_data.world == '{actual_world}'"
            status = VerificationStatus.PASS if actual_world == expected_world else VerificationStatus.FAIL

        elif req_type == "captures":
            min_caps = int(req.get("expected", 1))
            actual_caps = int(media.get("captures_count", 0))
            observed_str = f"{actual_caps} images captured"
            evidence_str = f"media.captures == {media.get('captures', [])}"
            status = VerificationStatus.PASS if actual_caps >= min_caps else VerificationStatus.FAIL

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
            # Custom requirement
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
