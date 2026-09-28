"""Canonical domain model for SkyTrack Missions independent of UI or GCS wire protocols."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CoordinateFrame(str, Enum):
    ENU = "ENU"  # East-North-Up (SkyTrack UI, plan.json, Path Planner API)
    NED = "NED"  # North-East-Down (PX4 Autopilot, wire frame to Mission Computer)
    WGS84 = "WGS84"  # Global Lat/Lng/Alt


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    DROP_PAYLOAD = "drop-ball"
    TAKE_SNAPSHOT = "take-snapshot"
    START_RECORDING = "start-recording-video"
    STOP_RECORDING = "stop-recording-video"
    START_SPRAYING = "start-spraying"
    STOP_SPRAYING = "stop-spraying"
    BREAK_RTL = "break-rtl"
    BREAK_LAND = "break-land"
    AI_FLOW = "ai-flow"
    TAKEOFF = "takeoff"
    LAND = "land"
    RTL = "rtl"


class Waypoint(BaseModel):
    """3D point representing an ENU waypoint."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    x: float = Field(description="East coordinate in meters")
    y: float = Field(description="North coordinate in meters")
    z: float = Field(description="Up altitude in meters")
    target_speed: float | None = Field(default=None, description="Leg speed in m/s")
    after_action: str | None = Field(
        default=None,
        description="Action attached at this waypoint: drop-ball, take-snapshot, etc.",
    )


class NoFlyZoneVolume(BaseModel):
    """3D No-Fly Zone representation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    frame: Literal["enu", "wgs84"] = "enu"
    inclusion: bool = False
    center: tuple[float, float] | None = None
    radius: float | None = None
    polygon: list[tuple[float, float]] | None = None
    z_min: float | None = None
    z_max: float | None = None


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationIssue(BaseModel):
    severity: ValidationSeverity
    code: str
    message: str
    action_index: int | None = None
    action_id: str | None = None
    fix_suggestion: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class CanonicalMission(BaseModel):
    """High-level canonical representation of a SkyTrack Mission."""

    model_config = ConfigDict(extra="ignore")

    project_id: str
    mission_id: str
    name: str = "Untitled Mission"
    world: str = "default"
    vehicle: str = "x500_livox_mid_360"
    code_mode: bool = False
    takeoff_altitude: float = 2.5
    target_speed: float = 2.0
    safety_option: Literal["avoid", "brake", "off"] = "avoid"
    end_action: Literal["rtl", "land"] = "rtl"
    spawn_location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    waypoints: list[Waypoint] = Field(default_factory=list)
    raw_actions: list[dict[str, Any]] = Field(default_factory=list)
    raw_plan: dict[str, Any] = Field(default_factory=dict, exclude=True)
    raw_mission: dict[str, Any] = Field(default_factory=dict, exclude=True)
    no_fly_zones: list[NoFlyZoneVolume] = Field(default_factory=list)
    python_script: str | None = None
