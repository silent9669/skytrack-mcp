"""Tests for SkyTrack Autonomy Levels 1-6 templates and semantic AST rules
(`GetSkyTrack/skytrack-autonomy-example` develop branch compliance).
"""

from __future__ import annotations

import pytest

from skytrack_mcp.server import (
    get_autonomy_level_template,
    get_uav_python_sdk_reference,
    validate_uav_python_code,
)


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_autonomy_level_templates_pass_validation(level: int) -> None:
    """Every Level 1..6 template must pass static & semantic validation with 0 errors."""
    tpl = get_autonomy_level_template(level=level)
    assert tpl["level"] == level
    code = tpl["code"]
    assert "from __future__ import annotations" in code
    assert "def scenario(" in code
    assert "def main() -> None:" in code

    val = validate_uav_python_code(code)
    assert val["valid"] is True, f"Level {level} failed validation: {val['errors']}"
    assert len(val["errors"]) == 0
    assert val["detected_level"] == level


def test_sdk_reference_includes_full_6_level_curriculum() -> None:
    """Verify get_uav_python_sdk_reference returns the 6-level curriculum and golden rules."""
    ref = get_uav_python_sdk_reference()
    assert "autonomy_levels_curriculum" in ref
    assert len(ref["autonomy_levels_curriculum"]) == 6
    assert "golden_architectural_rules" in ref
    assert "VideoRecorder" in ref["function_signatures"]
    assert "Sprayer" in ref["function_signatures"]
    assert "Detector" in ref["function_signatures"]


def test_validator_catches_battery_percent_scale_pitfall() -> None:
    """Verify `battery.percent < 0.4` (0.0-1.0 instead of 0-100) is flagged as an error."""
    bad_battery_code = '''
from __future__ import annotations
from local_planner import boot_drone, takeoff, land

def scenario(ctx):
    yield takeoff(alt_m=3.0)
    if ctx.senses.battery.percent < 0.4:
        yield land()
    yield land()

scenario.requires_senses = ["pose", "obstacle", "status", "battery"]
'''
    val = validate_uav_python_code(bad_battery_code)
    assert val["valid"] is False
    assert any("0-100 scale" in err for err in val["errors"])


def test_validator_catches_blocking_sleep_in_custom_skill() -> None:
    """Verify `time.sleep()` or `time.time()` inside a custom Skill is flagged as an error."""
    bad_skill_code = '''
from __future__ import annotations
import time
from local_planner import Skill, boot_drone, takeoff, land

class BadBlockingSkill(Skill):
    def start(self, ctx):
        time.sleep(2.0)
        self._t0 = time.time()
    def cancel(self):
        pass
    @property
    def is_done(self):
        return True

def scenario(ctx):
    yield takeoff(alt_m=3.0)
    yield land()
'''
    val = validate_uav_python_code(bad_skill_code)
    assert val["valid"] is False
    assert "BadBlockingSkill" in val["custom_components"]["skills"]
    assert any("never block with time.sleep()" in err for err in val["errors"])


def test_validator_catches_setpoint_or_control_group_in_custom_service() -> None:
    """Verify custom Service calling `publish_trajectory_setpoint` or `ScheduleGroup.CONTROL` is flagged."""
    bad_service_code = '''
from __future__ import annotations
from local_planner import boot_drone, takeoff, land

class BadTelemetryService:
    def attach(self, world):
        world.schedule(0.05, self.tick, group=ScheduleGroup.CONTROL)
        world.publish_trajectory_setpoint(0.0, 0.0, -3.0, 0.0)
    def tick(self):
        pass
    def shutdown(self):
        pass

def scenario(ctx):
    yield takeoff(alt_m=3.0)
    yield land()
'''
    val = validate_uav_python_code(bad_service_code)
    assert val["valid"] is False
    assert "BadTelemetryService" in val["custom_components"]["services"]
    assert any("publish_trajectory_setpoint" in err for err in val["errors"])
    assert any("ScheduleGroup.MEDIA" in err for err in val["errors"])
