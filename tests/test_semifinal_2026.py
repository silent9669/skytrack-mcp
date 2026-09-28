from __future__ import annotations

import math

import pytest

from skytrack_mcp.scenarios.semifinal_2026 import (
    AREA_HECTARES,
    CHARGING_PADS_ENU,
    MAX_FLIGHT_ALTITUDE_M,
    MAX_FLIGHT_DURATION_S,
    MAX_MISSION_DURATION_S,
    MAX_VALID_SPRAY_ALTITUDE_M,
    MIN_RESIDENTIAL_CLEARANCE_M,
    MODEL_CLASSES,
    MODEL_ID,
    MODEL_ONNX_SHA256,
    MODEL_ZIP_SHA256,
    PARCEL_COUNT,
    TOUCHDOWN_RADIUS_M,
    VEHICLE_MODEL,
    WORLD_NAME,
    compute_spray_swath_and_dose,
    evaluate_semifinal_compliance,
    project_pixel_bbox_to_enu,
)


def test_semifinal_pack_contains_public_scenario_limits_and_model_identity() -> None:
    assert WORLD_NAME == "An Giang (outdoor)"
    assert VEHICLE_MODEL == "x500_spray"
    assert AREA_HECTARES == 28.65
    assert PARCEL_COUNT == 130
    assert MAX_FLIGHT_ALTITUDE_M == 40.0
    assert MAX_VALID_SPRAY_ALTITUDE_M == 20.0
    assert MIN_RESIDENTIAL_CLEARANCE_M == 5.0
    assert TOUCHDOWN_RADIUS_M == 3.0
    assert MAX_FLIGHT_DURATION_S == 900.0
    assert MAX_MISSION_DURATION_S == 5400.0
    assert MODEL_ID == "det-h2026-v26n-b-fp32-640"
    assert MODEL_CLASSES == ["stressed"]
    assert (
        MODEL_ZIP_SHA256
        == "18e86fda14a9d914aff7915c9c3da67b1a92103c92537c944bf2089f4f814f0e"
    )
    assert (
        MODEL_ONNX_SHA256
        == "6352161daca9e52ac6ef35916ef584062c8b8cb24c7915155ce6b21b910ee58f"
    )
    assert CHARGING_PADS_ENU == {
        "CS1": (0.0, 0.0, 0.0),
        "CS2": (329.32, -234.73, -1.0),
        "CS3": (356.43, -654.32, 0.0),
        "CS4": (41.72, -582.67, -1.1),
    }


def test_pixel_bbox_projects_enu_corners_using_camera_geometry() -> None:
    pixel_half_width = 26.9968
    polygon = project_pixel_bbox_to_enu(
        320.0 - pixel_half_width,
        240.0 - pixel_half_width,
        320.0 + pixel_half_width,
        240.0 + pixel_half_width,
        pose_north=10.0,
        pose_east=20.0,
        pose_z_ned=-4.783,
        heading_rad=0.0,
    )

    assert polygon == pytest.approx(
        [
            (19.5, 10.625),
            (20.5, 10.625),
            (20.5, 9.625),
            (19.5, 9.625),
        ],
        abs=1e-5,
    )


def test_spray_helper_calculates_swath_and_target_dose_band() -> None:
    result = compute_spray_swath_and_dose(alt_m=5.0, speed_mps=2.0)

    expected_swath = 0.536 * (5.0 + 0.117)
    assert result["swath_width_m"] == pytest.approx(expected_swath)
    assert result["dose_ml_m2"] == pytest.approx(16.67 * 0.7 / (expected_swath * 2.0))
    assert result["within_target_dose_band"] is True


def test_spray_helper_rejects_nonpositive_altitude_or_speed() -> None:
    with pytest.raises(ValueError):
        compute_spray_swath_and_dose(alt_m=0.0, speed_mps=2.0)
    with pytest.raises(ValueError):
        compute_spray_swath_and_dose(alt_m=5.0, speed_mps=0.0)


def test_compliance_is_unknown_without_measured_safety_evidence() -> None:
    result = evaluate_semifinal_compliance()

    assert result["safety_policy"] == "UNKNOWN"
    assert result["model_availability"] == "UNKNOWN"
    assert result["perception_provenance"] == "UNKNOWN"
    assert result["semifinal_output_schema"] == "UNKNOWN"


def test_compliance_passes_only_when_known_limits_and_model_match() -> None:
    result = evaluate_semifinal_compliance(
        world=WORLD_NAME,
        vehicle=VEHICLE_MODEL,
        flight_altitude_m=40.0,
        spray_altitude_m=20.0,
        residential_clearance_m=5.0,
        sprayed_in_residential_buffer=False,
        charging_pad_id="CS2",
        touchdown_distance_m=3.0,
        flight_duration_s=900.0,
        total_mission_duration_s=5400.0,
        model_catalogue_available=True,
        model_id=MODEL_ID,
        model_classes=["stressed"],
        model_zip_sha256=MODEL_ZIP_SHA256,
        model_onnx_sha256=MODEL_ONNX_SHA256,
        route_geometry_clear=True,
        terrain_clear=True,
        no_fly_zones_clear=True,
        pad_identity_verified=True,
        charging_protocol_verified=True,
        perception_verified=True,
    )

    assert result["safety_policy"] == "PASS"
    assert result["model_availability"] == "AVAILABLE"
    assert result["perception_provenance"] == "VERIFIED"
    assert result["semifinal_output_schema"] == "UNKNOWN"


def test_compliance_allows_residential_buffer_entry_only_for_a_verified_pad_landing() -> (
    None
):
    result = evaluate_semifinal_compliance(
        world=WORLD_NAME,
        vehicle=VEHICLE_MODEL,
        flight_altitude_m=5.0,
        spray_altitude_m=5.0,
        residential_clearance_m=4.0,
        sprayed_in_residential_buffer=False,
        landing_only_pad_approach=True,
        charging_pad_id="CS1",
        touchdown_distance_m=2.0,
        flight_duration_s=300.0,
        total_mission_duration_s=600.0,
        route_geometry_clear=True,
        terrain_clear=True,
        no_fly_zones_clear=True,
        pad_identity_verified=True,
        charging_protocol_verified=True,
    )

    assert result["safety_policy"] == "PASS"


def test_compliance_fails_for_residential_spray_and_marks_unknown_fields() -> None:
    result = evaluate_semifinal_compliance(
        world=WORLD_NAME,
        vehicle=VEHICLE_MODEL,
        flight_altitude_m=10.0,
        spray_altitude_m=5.0,
        residential_clearance_m=6.0,
        sprayed_in_residential_buffer=True,
        charging_pad_id="CS1",
        touchdown_distance_m=1.0,
        flight_duration_s=300.0,
        total_mission_duration_s=600.0,
    )

    assert result["safety_policy"] == "FAIL"
    assert result["model_availability"] == "UNKNOWN"
    assert result["perception_provenance"] == "UNKNOWN"
    assert result["semifinal_output_schema"] == "UNKNOWN"


def test_camera_projection_uses_heading_to_rotate_body_offsets() -> None:
    polygon = project_pixel_bbox_to_enu(
        320.0,
        240.0,
        320.0,
        240.0,
        pose_north=10.0,
        pose_east=20.0,
        pose_z_ned=-1.0,
        heading_rad=math.pi / 2,
    )

    assert polygon == pytest.approx([(20.125, 10.0)] * 4)
