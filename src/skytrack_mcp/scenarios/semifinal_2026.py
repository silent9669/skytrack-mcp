"""Public 2026 semifinal agriculture constraints and measured-evidence helpers.

The output/report schema remains UNKNOWN until verified against a native report or
another authorized SkyTrack App contract. Static calculations are not flight evidence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

WORLD_NAME = "An Giang (outdoor)"
VEHICLE_MODEL = "x500_spray"
AREA_HECTARES = 28.65
PARCEL_COUNT = 130

MAX_FLIGHT_ALTITUDE_M = 40.0
MAX_VALID_SPRAY_ALTITUDE_M = 20.0
MIN_RESIDENTIAL_CLEARANCE_M = 5.0
CHARGING_PADS_ENU = {
    "CS1": (0.0, 0.0, 0.0),
    "CS2": (329.32, -234.73, -1.0),
    "CS3": (356.43, -654.32, 0.0),
    "CS4": (41.72, -582.67, -1.1),
}
TOUCHDOWN_RADIUS_M = 3.0
MAX_FLIGHT_DURATION_MIN = 15.0
MAX_FLIGHT_DURATION_S = MAX_FLIGHT_DURATION_MIN * 60.0
MAX_MISSION_DURATION_MIN = 90.0
MAX_MISSION_DURATION_S = MAX_MISSION_DURATION_MIN * 60.0

MODEL_ID = "det-h2026-v26n-b-fp32-640"
MODEL_CLASSES = ["stressed"]
MODEL_ZIP_SHA256 = "18e86fda14a9d914aff7915c9c3da67b1a92103c92537c944bf2089f4f814f0e"
MODEL_ONNX_SHA256 = "6352161daca9e52ac6ef35916ef584062c8b8cb24c7915155ce6b21b910ee58f"

CAMERA_FX = 269.968
CAMERA_FY = 269.968
CAMERA_CX = 320.0
CAMERA_CY = 240.0
CAMERA_HEIGHT_OFFSET_M = 0.217
CAMERA_FORWARD_OFFSET_M = 0.125
NOZZLE_HEIGHT_OFFSET_M = 0.117
SPRAY_CONE_ANGLE_DEG = 30.0
SPRAY_SWATH_FACTOR = 0.536
SPRAY_FLOW_RATE_ML_S = 16.67
SPRAY_EFFICIENCY = 0.7
MIN_TARGET_DOSE_ML_M2 = 1.0
MAX_TARGET_DOSE_ML_M2 = 3.0


def project_pixel_bbox_to_enu(
    u_min: float,
    v_min: float,
    u_max: float,
    v_max: float,
    pose_north: float,
    pose_east: float,
    pose_z_ned: float,
    heading_rad: float,
) -> list[tuple[float, float]]:
    """Project image-box corners to (east, north) using the published nadir camera model."""
    if u_min > u_max or v_min > v_max:
        raise ValueError(
            "Bounding-box minimum coordinates must not exceed maximum coordinates."
        )

    height_m = -pose_z_ned + CAMERA_HEIGHT_OFFSET_M
    if height_m <= 0.0:
        raise ValueError("Camera height above ground must be positive.")

    cos_heading = math.cos(heading_rad)
    sin_heading = math.sin(heading_rad)
    camera_east = pose_east + CAMERA_FORWARD_OFFSET_M * sin_heading
    camera_north = pose_north + CAMERA_FORWARD_OFFSET_M * cos_heading
    corners = ((u_min, v_min), (u_max, v_min), (u_max, v_max), (u_min, v_max))
    polygon: list[tuple[float, float]] = []
    for u, v in corners:
        right_m = (u - CAMERA_CX) / CAMERA_FX * height_m
        back_m = (v - CAMERA_CY) / CAMERA_FY * height_m
        east = camera_east + right_m * cos_heading - back_m * sin_heading
        north = camera_north - right_m * sin_heading - back_m * cos_heading
        polygon.append((east, north))
    return polygon


def compute_spray_swath_and_dose(alt_m: float, speed_mps: float) -> dict[str, Any]:
    """Estimate a straight-leg spray swath and centerline dose at constant speed."""
    if alt_m <= 0.0:
        raise ValueError("Spray altitude must be positive.")
    if speed_mps <= 0.0:
        raise ValueError("Spray speed must be positive.")

    nozzle_height_m = alt_m + NOZZLE_HEIGHT_OFFSET_M
    swath_width_m = SPRAY_SWATH_FACTOR * nozzle_height_m
    dose_ml_m2 = SPRAY_FLOW_RATE_ML_S * SPRAY_EFFICIENCY / (swath_width_m * speed_mps)
    return {
        "nozzle_height_m": nozzle_height_m,
        "swath_width_m": swath_width_m,
        "dose_ml_m2": dose_ml_m2,
        "within_target_dose_band": MIN_TARGET_DOSE_ML_M2
        <= dose_ml_m2
        <= MAX_TARGET_DOSE_ML_M2,
    }


def evaluate_semifinal_compliance(
    *,
    world: str | None = None,
    vehicle: str | None = None,
    flight_altitude_m: float | None = None,
    spray_altitude_m: float | None = None,
    residential_clearance_m: float | None = None,
    sprayed_in_residential_buffer: bool | None = None,
    landing_only_pad_approach: bool | None = None,
    charging_pad_id: str | None = None,
    touchdown_distance_m: float | None = None,
    flight_duration_s: float | None = None,
    total_mission_duration_s: float | None = None,
    route_geometry_clear: bool | None = None,
    terrain_clear: bool | None = None,
    no_fly_zones_clear: bool | None = None,
    pad_identity_verified: bool | None = None,
    charging_protocol_verified: bool | None = None,
    model_catalogue_available: bool | None = None,
    model_id: str | None = None,
    model_classes: Sequence[str] | None = None,
    model_zip_sha256: str | None = None,
    model_onnx_sha256: str | None = None,
    perception_verified: bool | None = None,
) -> dict[str, str]:
    """Evaluate public constraints without treating missing evidence as a pass.

    `charging_protocol_verified` means the selected runtime establishes Mission Break,
    pad landing, recharge, and manual user resume. Geometry, terrain, and no-fly checks
    must be established independently by trustworthy route/world evidence.
    """
    failures: list[str] = []
    unknowns: list[str] = []

    if world is None:
        unknowns.append("world")
    elif world != WORLD_NAME:
        failures.append("world")
    if vehicle is None:
        unknowns.append("vehicle")
    elif vehicle != VEHICLE_MODEL:
        failures.append("vehicle")

    if flight_altitude_m is None:
        unknowns.append("flight altitude")
    elif not 0.0 <= flight_altitude_m <= MAX_FLIGHT_ALTITUDE_M:
        failures.append("flight altitude")
    if spray_altitude_m is None:
        unknowns.append("spray altitude")
    elif not 0.0 < spray_altitude_m <= MAX_VALID_SPRAY_ALTITUDE_M:
        failures.append("spray altitude")

    if residential_clearance_m is None:
        unknowns.append("residential clearance")
    elif residential_clearance_m < MIN_RESIDENTIAL_CLEARANCE_M:
        if landing_only_pad_approach is False:
            failures.append("residential clearance")
        elif landing_only_pad_approach is None:
            unknowns.append("landing-only pad approach exception")
    if sprayed_in_residential_buffer is True:
        failures.append("spraying in residential buffer")
    elif sprayed_in_residential_buffer is None:
        unknowns.append("residential spray exclusion")

    if charging_pad_id is None:
        unknowns.append("charging pad identity")
    elif charging_pad_id not in CHARGING_PADS_ENU:
        failures.append("charging pad identity")
    if touchdown_distance_m is None:
        unknowns.append("pad touchdown distance")
    elif not 0.0 <= touchdown_distance_m <= TOUCHDOWN_RADIUS_M:
        failures.append("pad touchdown distance")
    if pad_identity_verified is None:
        unknowns.append("installed charging-pad verification")
    elif not pad_identity_verified:
        failures.append("installed charging-pad verification")

    if flight_duration_s is None:
        unknowns.append("per-charge flight duration")
    elif not 0.0 <= flight_duration_s <= MAX_FLIGHT_DURATION_S:
        failures.append("per-charge flight duration")
    if total_mission_duration_s is None:
        unknowns.append("total mission duration")
    elif not 0.0 <= total_mission_duration_s <= MAX_MISSION_DURATION_S:
        failures.append("total mission duration")

    for label, value in (
        ("route geometry", route_geometry_clear),
        ("terrain coverage", terrain_clear),
        ("no-fly-zone clearance", no_fly_zones_clear),
        ("Mission Break/recharge/resume protocol", charging_protocol_verified),
    ):
        if value is None:
            unknowns.append(label)
        elif not value:
            failures.append(label)

    if (
        residential_clearance_m is not None
        and residential_clearance_m < MIN_RESIDENTIAL_CLEARANCE_M
    ):
        exception_evidence = (
            landing_only_pad_approach is True
            and charging_pad_id in CHARGING_PADS_ENU
            and touchdown_distance_m is not None
            and touchdown_distance_m <= TOUCHDOWN_RADIUS_M
            and pad_identity_verified is True
            and sprayed_in_residential_buffer is False
        )
        if exception_evidence:
            failures = [
                failure for failure in failures if failure != "residential clearance"
            ]
        elif landing_only_pad_approach is True:
            if (
                charging_pad_id is None
                or touchdown_distance_m is None
                or pad_identity_verified is None
            ):
                unknowns.append("landing-only pad approach evidence")
            else:
                failures.append("landing-only pad approach evidence")

    safety_policy = "FAIL" if failures else "UNKNOWN" if unknowns else "PASS"

    if model_catalogue_available is False:
        model_availability = "NOT_AVAILABLE"
    elif model_catalogue_available is None:
        model_availability = "UNKNOWN"
    elif model_catalogue_available is True:
        supplied_identity = (
            model_id,
            model_classes,
            model_zip_sha256,
            model_onnx_sha256,
        )
        if any(value is None for value in supplied_identity):
            model_availability = "UNKNOWN"
        elif (
            model_id != MODEL_ID
            or list(model_classes or []) != MODEL_CLASSES
            or model_zip_sha256 != MODEL_ZIP_SHA256
            or model_onnx_sha256 != MODEL_ONNX_SHA256
        ):
            model_availability = "NOT_AVAILABLE"
        else:
            model_availability = "AVAILABLE"

    perception_provenance = "VERIFIED" if perception_verified is True else "UNKNOWN"
    return {
        "safety_policy": safety_policy,
        "model_availability": model_availability,
        "perception_provenance": perception_provenance,
        "semifinal_output_schema": "UNKNOWN",
    }
