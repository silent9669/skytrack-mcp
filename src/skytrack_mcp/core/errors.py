"""Structured error taxonomy for SkyTrack MCP."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class SkyTrackErrorCode(str, Enum):
    # Application & Environment
    SKYTRACK_NOT_RUNNING = "SKYTRACK_NOT_RUNNING"
    SKYTRACK_NOT_READY = "SKYTRACK_NOT_READY"
    DOCKER_NOT_RUNNING = "DOCKER_NOT_RUNNING"
    SIMULATOR_NOT_READY = "SIMULATOR_NOT_READY"
    CONTAINER_NOT_FOUND = "CONTAINER_NOT_FOUND"

    # Mission & Project
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    MISSION_NOT_FOUND = "MISSION_NOT_FOUND"
    MISSION_INVALID = "MISSION_INVALID"
    MISSION_WRITE_FAILED = "MISSION_WRITE_FAILED"
    MISSION_PARSE_FAILED = "MISSION_PARSE_FAILED"

    # World & Vehicle
    WORLD_NOT_FOUND = "WORLD_NOT_FOUND"
    VEHICLE_NOT_FOUND = "VEHICLE_NOT_FOUND"
    COLLISION_DETECTED = "COLLISION_DETECTED"

    # UI & Computer Use
    UI_TARGET_NOT_FOUND = "UI_TARGET_NOT_FOUND"
    UI_STATE_MISMATCH = "UI_STATE_MISMATCH"
    WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"

    # Simulation & Execution
    SIMULATION_START_FAILED = "SIMULATION_START_FAILED"
    SIMULATION_TIMEOUT = "SIMULATION_TIMEOUT"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    TELEMETRY_UNAVAILABLE = "TELEMETRY_UNAVAILABLE"

    # Reports
    REPORT_NOT_AVAILABLE = "REPORT_NOT_AVAILABLE"
    REPORT_PARSE_FAILED = "REPORT_PARSE_FAILED"

    # Cloud & Auth
    AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    CLOUD_API_ERROR = "CLOUD_API_ERROR"

    # General
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SkyTrackError(Exception):
    """Base exception for all structured SkyTrack MCP errors."""

    def __init__(
        self,
        code: SkyTrackErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.suggested_action = suggested_action

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "error_code": self.code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.suggested_action:
            result["suggested_action"] = self.suggested_action
        return result
