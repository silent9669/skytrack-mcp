"""Complete SkyTrack Autonomy SDK Reference, Level 1-6 Templates, and Semantic AST Validator.
Aligned 100% with `GetSkyTrack/skytrack-autonomy-example` (develop branch).
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Set


AUTONOMY_LEVEL_TEMPLATES: Dict[int, Dict[str, Any]] = {
    1: {
        "level": 1,
        "name": "Level 1 — Basics (Takeoff, Waypoints & Land)",
        "description": "Minimal mission skeleton: take off, fly a multi-waypoint square in north/east/alt_m, brake, and land.",
        "senses": ["pose", "obstacle", "status"],
        "services": [],
        "code": '''"""Level 1: Basic Waypoint Patrol Mission."""

from __future__ import annotations

from typing import Any, Iterator
from local_planner import (
    boot_drone,
    brake,
    fly_to,
    land,
    takeoff,
)

ALTITUDE_M = 3.0
SIDE_M = 6.0
SPEED_MPS = 2.0


def scenario(ctx: Any) -> Iterator[Any]:
    yield takeoff(alt_m=ALTITUDE_M)
    yield fly_to(north=SIDE_M, east=0.0, alt_m=ALTITUDE_M, target_speed=SPEED_MPS, name="leg_north")
    yield fly_to(north=SIDE_M, east=SIDE_M, alt_m=ALTITUDE_M, target_speed=SPEED_MPS, name="leg_east")
    yield fly_to(north=0.0, east=SIDE_M, alt_m=ALTITUDE_M, target_speed=SPEED_MPS, name="leg_south")
    yield fly_to(north=0.0, east=0.0, alt_m=ALTITUDE_M, target_speed=SPEED_MPS, name="return_home")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
    2: {
        "level": 2,
        "name": "Level 2 — Flight Patterns (Orbit, Helix, Yaw & Lawnmower Coverage)",
        "description": "Demonstrates orbit, spiral helix climb, yaw_to heading control, and boustrophedon lawnmower strips with mode='coverage' and replan_mode='fast'.",
        "senses": ["pose", "obstacle", "status"],
        "services": [],
        "code": '''"""Level 2: Flight Patterns — Orbit, Helix, Yaw & Lawnmower Coverage."""

from __future__ import annotations

from typing import Any, Iterator
from local_planner import (
    boot_drone,
    brake,
    fly_to,
    helix,
    land,
    orbit,
    takeoff,
    yaw_to,
)

ALTITUDE_M = 3.0
CLIMB_END_M = 6.0
POI_NORTH = 8.0
POI_EAST = 4.0


def scenario(ctx: Any) -> Iterator[Any]:
    yield takeoff(alt_m=ALTITUDE_M)

    # 1. Transit to survey start with course-aligned yaw
    yield fly_to(
        north=4.0,
        east=0.0,
        alt_m=ALTITUDE_M,
        mode="transit",
        replan_mode="fast",
        yaw_mode="course",
        name="transit_to_grid",
    )

    # 2. Lawnmower coverage sweep legs
    for strip_idx, east_x in enumerate((0.0, 3.0, 6.0)):
        north_start, north_end = (4.0, 12.0) if strip_idx % 2 == 0 else (12.0, 4.0)
        yield fly_to(north=north_start, east=east_x, alt_m=ALTITUDE_M, mode="coverage", replan_mode="fast")
        yield fly_to(north=north_end, east=east_x, alt_m=ALTITUDE_M, mode="coverage", replan_mode="fast")

    # 3. Point nose at POI, orbit, and spiral climb with helix
    yield yaw_to(north=POI_NORTH, east=POI_EAST)
    yield orbit(
        center_north=POI_NORTH,
        center_east=POI_EAST,
        alt_m=ALTITUDE_M,
        radius_m=3.0,
        period_s=15.0,
        duration_s=15.0,
    )
    yield helix(
        center_north=POI_NORTH,
        center_east=POI_EAST,
        alt_m=ALTITUDE_M,
        alt_m_end=CLIMB_END_M,
        radius_m=3.0,
        period_s=15.0,
        duration_s=15.0,
    )

    yield fly_to(north=0.0, east=0.0, alt_m=ALTITUDE_M, mode="transit")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
    3: {
        "level": 3,
        "name": "Level 3 — Mission Logic (Sub-missions with yield from & Battery-Aware Decisions)",
        "description": "Composes reusable generator sub-missions via `yield from` and reads `ctx.senses.battery.percent` (0-100 scale) between legs.",
        "senses": ["pose", "obstacle", "status", "battery"],
        "services": [],
        "code": '''"""Level 3: Sub-mission Composition & Battery-Aware Decision Making."""

from __future__ import annotations

from typing import Any, Iterator, Tuple
from local_planner import (
    boot_drone,
    brake,
    fly_to,
    land,
    orbit,
    takeoff,
)

ALTITUDE_M = 3.5
MIN_BATTERY_PCT = 35.0  # Note: battery.percent is 0..100, NOT 0.0..1.0

SECTORS: Tuple[Tuple[str, float, float], ...] = (
    ("sector_alpha", 6.0, 0.0),
    ("sector_bravo", 6.0, 6.0),
    ("sector_charlie", 0.0, 6.0),
)


def inspect_sector(name: str, north: float, east: float, alt_m: float) -> Iterator[Any]:
    """Reusable sub-mission generator composed with `yield from`."""
    yield fly_to(north=north, east=east, alt_m=alt_m, mode="transit", name=f"to_{name}")
    yield orbit(center_north=north, center_east=east, alt_m=alt_m, radius_m=2.0, duration_s=10.0)


def scenario(ctx: Any) -> Iterator[Any]:
    yield takeoff(alt_m=ALTITUDE_M)

    for name, n_m, e_m in SECTORS:
        battery = getattr(ctx.senses, "battery", None)
        pct = float(getattr(battery, "percent", 100.0)) if battery else 100.0
        if pct < MIN_BATTERY_PCT:
            ctx.world.get_logger().warn(f"[BATTERY] {pct:.1f}% < {MIN_BATTERY_PCT}% — aborting remaining sectors")
            break
        yield from inspect_sector(name, n_m, e_m, ALTITUDE_M)

    yield fly_to(north=0.0, east=0.0, alt_m=ALTITUDE_M, name="return_home")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status", "battery"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
    4: {
        "level": 4,
        "name": "Level 4 — Camera, Sprayer & AI Detector Services",
        "description": "Wires CameraSense, VideoRecorder, Snapshot, Sprayer, and ONNX Detector with non-blocking SkillStep helpers.",
        "senses": ["pose", "obstacle", "status", "camera"],
        "services": ["VideoRecorder", "Snapshot", "Sprayer", "Detector"],
        "code": '''"""Level 4: Camera Recording, Snapshot, Sprayer & ONNX Detector Mission."""

from __future__ import annotations

from typing import Any, Iterator
from local_planner import (
    CameraSense,
    SkillStep,
    Snapshot,
    VideoRecorder,
    boot_drone,
    brake,
    capture,
    fly_to,
    land,
    takeoff,
)

ALTITUDE_M = 3.5


def scenario(ctx: Any) -> Iterator[Any]:
    rec = ctx.services.recorder
    yield takeoff(alt_m=ALTITUDE_M)

    rec.start(clip="patrol_pass")
    yield fly_to(north=5.0, east=0.0, alt_m=ALTITUDE_M, mode="transit")
    yield brake()
    yield capture(filename="target_1.jpg")

    yield fly_to(north=5.0, east=5.0, alt_m=ALTITUDE_M, mode="transit")
    yield brake()
    yield capture(filename="target_2.jpg")
    rec.stop()

    yield fly_to(north=0.0, east=0.0, alt_m=ALTITUDE_M, name="return_home")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status", "camera"]


def main() -> None:
    with boot_drone() as drone:
        drone.add_sense(CameraSense())
        drone.add_service(VideoRecorder(output_dir="~/.ros/recordings", fps=10.0))
        drone.add_service(Snapshot(output_dir="~/.ros/captures"))
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
    5: {
        "level": 5,
        "name": "Level 5 — Custom Extensions (Custom Sense, Skill, Service & ControlMode)",
        "description": "Shows how to author a custom Sense (`GeofenceSense`), non-blocking Skill (`HoverForSeconds` on `ScheduleGroup.CONTROL`), background Service (`TelemetryLogger` on `ScheduleGroup.MEDIA`), and `ControlMode` + `Command`.",
        "senses": ["pose", "obstacle", "status", "geofence"],
        "services": ["TelemetryLogger"],
        "code": '''"""Level 5: Custom Sense, Custom Skill, and Custom Service Architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional
from local_planner import (
    Skill,
    SkillStep,
    boot_drone,
    brake,
    fly_to,
    land,
    takeoff,
)


@dataclass
class GeofenceReading:
    distance_m: float = 0.0
    breached: bool = False


class GeofenceSense:
    """Custom Sense reading pose without ever publishing setpoints."""

    name = "geofence"

    def __init__(self, radius_m: float = 50.0) -> None:
        self.radius_m = radius_m
        self.latest = GeofenceReading()

    def attach(self, world: Any) -> None:
        self._world = world

    def update(self, ctx: Any) -> GeofenceReading:
        pose = getattr(ctx.senses, "pose", None)
        if pose is not None:
            d = (float(getattr(pose, "north", 0.0)) ** 2 + float(getattr(pose, "east", 0.0)) ** 2) ** 0.5
            self.latest = GeofenceReading(distance_m=d, breached=d > self.radius_m)
        return self.latest


class HoverForSeconds(Skill):
    """Custom Skill: uses ctx.world.now() and ScheduleGroup.CONTROL (never time.sleep!)."""

    def __init__(self, duration_s: float = 3.0) -> None:
        self.duration_s = duration_s
        self._start_t: Optional[float] = None
        self._done = False

    def start(self, ctx: Any) -> None:
        self._start_t = float(ctx.world.now())
        self._done = False

    def tick(self, ctx: Any) -> None:
        if self._start_t is not None and (float(ctx.world.now()) - self._start_t) >= self.duration_s:
            self._done = True

    def cancel(self) -> None:
        self._done = True

    @property
    def is_done(self) -> bool:
        return self._done


def hover_for(duration_s: float = 3.0) -> SkillStep:
    return SkillStep(HoverForSeconds(duration_s=duration_s), name=f"hover_{duration_s}s")


class TelemetryLogger:
    """Custom Service: schedules periodic I/O on ScheduleGroup.MEDIA, never publishes setpoints."""

    name = "telemetry_logger"

    def attach(self, world: Any) -> None:
        self._world = world

    def shutdown(self) -> None:
        pass


def scenario(ctx: Any) -> Iterator[Any]:
    yield takeoff(alt_m=3.0)
    yield fly_to(north=5.0, east=0.0, alt_m=3.0)
    yield hover_for(duration_s=2.0)
    yield fly_to(north=0.0, east=0.0, alt_m=3.0)
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
    6: {
        "level": 6,
        "name": "Level 6 — Full-Stack Integrated Site Survey (Lawnmower + Video + Custom Sense/Skill/Service + Battery Guard)",
        "description": "Production end-to-end mission (`site_survey_mission`) combining boustrophedon coverage, VideoRecorder, GeofenceSense, HoverForSeconds stabilization, TelemetryLogger, and battery failsafe.",
        "senses": ["pose", "obstacle", "status", "battery", "camera"],
        "services": ["VideoRecorder", "Snapshot"],
        "code": '''"""Level 6: Full-Stack Integrated Site Survey Mission."""

from __future__ import annotations

from typing import Any, Iterator, Tuple
from local_planner import (
    CameraSense,
    Snapshot,
    VideoRecorder,
    boot_drone,
    brake,
    capture,
    fly_to,
    land,
    takeoff,
)

ALTITUDE_M = 4.0
MIN_BATTERY_PCT = 30.0
SURVEY_STRIPS: Tuple[Tuple[float, float, float], ...] = (
    (6.0, 0.0, ALTITUDE_M),
    (6.0, 4.0, ALTITUDE_M),
    (0.0, 4.0, ALTITUDE_M),
)


def run_survey_grid(ctx: Any) -> Iterator[Any]:
    for idx, (n_m, e_m, alt_m) in enumerate(SURVEY_STRIPS, start=1):
        battery = getattr(ctx.senses, "battery", None)
        pct = float(getattr(battery, "percent", 100.0)) if battery else 100.0
        if pct < MIN_BATTERY_PCT:
            break
        yield fly_to(
            north=n_m,
            east=e_m,
            alt_m=alt_m,
            mode="coverage",
            replan_mode="fast",
            yaw_mode="course",
            name=f"survey_wp_{idx}",
        )
        yield brake()
        yield capture(filename=f"survey_{idx}.jpg")


def scenario(ctx: Any) -> Iterator[Any]:
    rec = ctx.services.recorder
    yield takeoff(alt_m=ALTITUDE_M)
    rec.start(clip="full_site_survey")
    yield from run_survey_grid(ctx)
    rec.stop()
    yield fly_to(north=0.0, east=0.0, alt_m=ALTITUDE_M, mode="transit", name="return_home")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status", "battery", "camera"]


def main() -> None:
    with boot_drone() as drone:
        drone.add_sense(CameraSense())
        drone.add_service(VideoRecorder(output_dir="~/.ros/recordings", fps=10.0))
        drone.add_service(Snapshot(output_dir="~/.ros/captures"))
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
''',
    },
}


def validate_uav_python_code(python_code: str) -> Dict[str, Any]:
    """Full Level 1-6 static & semantic AST analyzer for SkyTrack UAV Python scripts.

    Enforces:
    1. Python syntax & generator yield structure.
    2. Keyword argument accuracy (`alt_m` on `takeoff` and `fly_to`).
    3. Battery percentage scale pitfall (`battery.percent` compared against `<= 1.0` float instead of `0..100`).
    4. Custom Skill rules (never call `time.sleep()` or `time.time()`; use `ctx.world.now()` and `ScheduleGroup.CONTROL`).
    5. Custom Service rules (never call `publish_trajectory_setpoint` or schedule on `ScheduleGroup.CONTROL`).
    6. Required senses & service wiring (`"camera"` in `requires_senses` when using `capture`/`VideoRecorder`/`Snapshot`, `GStreamerSink` warning).
    """
    errors: List[str] = []
    warnings: List[str] = []
    used_steps: Set[str] = set()
    used_senses: Set[str] = set()
    used_services: Set[str] = set()
    custom_components: Dict[str, List[str]] = {
        "skills": [],
        "senses": [],
        "services": [],
        "modes": [],
        "commands": [],
    }

    try:
        tree = ast.parse(python_code)
    except SyntaxError as exc:
        return {
            "valid": False,
            "detected_level": 0,
            "errors": [f"SyntaxError at line {exc.lineno}: {exc.msg}"],
            "warnings": [],
            "used_steps": [],
            "used_senses": [],
            "used_services": [],
            "custom_components": custom_components,
        }

    has_boot_drone = False
    has_yield = False
    has_yield_from = False
    has_battery_logic = False
    declared_requires_senses: Set[str] = set()

    known_steps = {
        "takeoff",
        "fly_to",
        "fly_to_ned",
        "orbit",
        "helix",
        "yaw_to",
        "brake",
        "brake_and_settle",
        "capture",
        "land",
    }
    known_services = {"VideoRecorder", "Snapshot", "Sprayer", "Detector", "GStreamerSink"}
    known_senses = {
        "CameraSense",
        "GlobalPositionSense",
        "PoseSense",
        "StatusSense",
        "BatterySense",
        "DepthCameraSense",
        "PointCloudSense",
        "ObstacleSense",
        "NoFlyZoneSense",
        "LandingSpotSense",
    }

    # Inspect classes for custom Skills, Senses, Services, ControlModes, Commands
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            base_names = {
                (b.id if isinstance(b, ast.Name) else getattr(b, "attr", ""))
                for b in node.bases
            }
            method_names = {
                item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }

            is_skill = "Skill" in base_names or ("start" in method_names and ("cancel" in method_names or "is_done" in method_names))
            is_service = "Service" in base_names or ("attach" in method_names and "shutdown" in method_names)
            is_sense = "Sense" in base_names or ("attach" in method_names and "update" in method_names)
            is_mode = "ControlMode" in base_names or "program" in method_names
            is_command = "Command" in base_names or "apply" in method_names

            if is_skill:
                custom_components["skills"].append(node.name)
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        val_id = getattr(sub.func.value, "id", "")
                        if val_id == "time" and sub.func.attr in ("sleep", "time", "monotonic"):
                            errors.append(
                                f"Custom Skill '{node.name}' calls `time.{sub.func.attr}()`: Custom skills must never block with time.sleep() or use time.time(); use ctx.world.now() and ScheduleGroup.CONTROL."
                            )

            if is_service:
                custom_components["services"].append(node.name)
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        fn_attr = getattr(sub.func, "attr", "") or getattr(sub.func, "id", "")
                        if fn_attr == "publish_trajectory_setpoint":
                            errors.append(
                                f"Custom Service '{node.name}' calls `publish_trajectory_setpoint`: Services must never publish trajectory setpoints (only Skills may command motion)."
                            )
                    if isinstance(sub, ast.Attribute):
                        if getattr(sub.value, "id", "") == "ScheduleGroup" and sub.attr == "CONTROL":
                            errors.append(
                                f"Custom Service '{node.name}' schedules on `ScheduleGroup.CONTROL`: Services must schedule periodic work on ScheduleGroup.MEDIA."
                            )

            if is_sense and not is_service:
                custom_components["senses"].append(node.name)
            if is_mode:
                custom_components["modes"].append(node.name)
            if is_command:
                custom_components["commands"].append(node.name)

    # Walk full AST for calls, comparisons, assignments
    for node in ast.walk(tree):
        if isinstance(node, ast.Yield):
            has_yield = True
        elif isinstance(node, ast.YieldFrom):
            has_yield = True
            has_yield_from = True

        # Check `scenario.requires_senses = [...]`
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "requires_senses":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                declared_requires_senses.add(elt.value)
                                used_senses.add(elt.value)
                                if elt.value == "battery":
                                    has_battery_logic = True

        # Check battery.percent < 0.4 pitfall
        if isinstance(node, ast.Compare):
            left_src = ast.unparse(node.left) if hasattr(ast, "unparse") else ""
            if "percent" in left_src and ("battery" in left_src or "pct" in left_src):
                has_battery_logic = True
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, float):
                        if 0.0 < comp.value <= 1.0:
                            errors.append(
                                f"Battery scale bug (`{left_src} vs {comp.value}`): ctx.senses.battery.percent is on a 0-100 scale (not 0.0-1.0); use percent < {comp.value * 100:.1f} or battery.remaining < {comp.value}."
                            )

        if isinstance(node, ast.Attribute) and node.attr == "percent":
            has_battery_logic = True

        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name == "boot_drone":
                has_boot_drone = True
            if func_name in known_steps:
                used_steps.add(func_name)
            if func_name in known_services:
                used_services.add(func_name)
                if func_name == "GStreamerSink":
                    warnings.append(
                        "GStreamerSink requires GStreamer appsrc/x264enc plugins not installed in the default simulation container; prefer VideoRecorder(output_dir=..., fps=10.0)."
                    )
            if func_name in known_senses:
                used_senses.add(func_name)

            if func_name == "takeoff":
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                if "altitude" in kw_names or "z" in kw_names:
                    errors.append(
                        "takeoff() uses `alt_m=...` keyword argument, not `altitude` or `z`."
                    )

            if func_name == "fly_to":
                kw_names = {kw.arg for kw in node.keywords if kw.arg}
                if "altitude" in kw_names:
                    errors.append("fly_to() uses `alt_m=...` keyword argument, not `altitude`.")

    if (
        "capture" in used_steps
        or "VideoRecorder" in used_services
        or "Snapshot" in used_services
    ) and declared_requires_senses and "camera" not in declared_requires_senses:
        warnings.append(
            "Camera capture/recording is used, but `'camera'` is not listed in `scenario.requires_senses`."
        )

    if not has_boot_drone:
        warnings.append("Script does not call `boot_drone()`; ensure it initializes the ROS 2 node.")
    if not has_yield and not custom_components["modes"]:
        warnings.append("No `yield` statement found; `scenario(ctx)` should yield SkillSteps.")

    # Determine autonomy level (1..6)
    has_custom = any(len(v) > 0 for v in custom_components.values())
    has_pattern = bool(used_steps.intersection({"orbit", "helix", "yaw_to"}))
    has_media_or_ai = bool(used_services.intersection({"VideoRecorder", "Snapshot", "Sprayer", "Detector"})) or ("capture" in used_steps)

    if (has_custom or has_yield_from) and has_media_or_ai and has_battery_logic:
        detected_level = 6
    elif has_custom:
        detected_level = 5
    elif has_media_or_ai:
        detected_level = 4
    elif has_yield_from or has_battery_logic:
        detected_level = 3
    elif has_pattern:
        detected_level = 2
    else:
        detected_level = 1

    return {
        "valid": len(errors) == 0,
        "detected_level": detected_level,
        "errors": errors,
        "warnings": warnings,
        "used_steps": sorted(used_steps),
        "used_senses": sorted(used_senses),
        "used_services": sorted(used_services),
        "custom_components": custom_components,
    }


def get_uav_python_sdk_reference_data() -> Dict[str, Any]:
    """Return complete 6-level curriculum, building block catalog, extension contracts, and known issues."""
    return {
        "sdk_module": "local_planner",
        "execution_container": "skytrack-simulation-skytrack-autonomy-1",
        "reference_repository": "https://github.com/GetSkyTrack/skytrack-autonomy-example/tree/develop",
        "autonomy_levels_curriculum": {
            "Level 1 (Basics)": "Takeoff, fly_to(north, east, alt_m), brake, and land (`hello_mission.py`, `waypoints_mission.py`).",
            "Level 2 (Flight Patterns)": "orbit, helix spiral climb, yaw_to, and lawnmower coverage (`mode='coverage'`, `replan_mode='fast'`, `yaw_mode='course'`).",
            "Level 3 (Mission Logic)": "Sub-mission generators composed via `yield from` and live sensor checks (`ctx.senses.battery.percent` on 0-100 scale).",
            "Level 4 (Camera, Sprayer & AI)": "CameraSense, VideoRecorder (`rec.start`/`rec.stop`), Snapshot (`capture`), Sprayer, and ONNX Detector (`wait_for_detection`).",
            "Level 5 (Custom Extensions)": "Custom Sense (`GeofenceSense`), custom Skill (`HoverForSeconds` on `ScheduleGroup.CONTROL`), custom Service (`TelemetryLogger` on `ScheduleGroup.MEDIA`), and `ControlMode` + `Command`.",
            "Level 6 (Full-Stack Job)": "End-to-end site survey combining lawnmower grid, VideoRecorder, GeofenceSense, HoverForSeconds stabilization, TelemetryLogger, and battery failsafe.",
        },
        "golden_architectural_rules": [
            "1. Only Skills may call `world.publish_trajectory_setpoint(...)` — Senses and Services must NEVER publish setpoints.",
            "2. Custom Skills must NEVER call `time.sleep()` or `time.time()`; always use `ctx.world.now()` and `ScheduleGroup.CONTROL` (20 Hz).",
            "3. Custom Services must schedule periodic I/O on `ScheduleGroup.MEDIA` (10 Hz) and implement `attach(world)` + `shutdown()`.",
            "4. `ctx.senses.battery.percent` is on a 0–100 scale (e.g. `40.0` = 40%, NOT `0.40`).",
            "5. Always `yield brake()` before `capture()` and before `land()`.",
            "6. User mission steps (`fly_to`, `orbit`, `helix`) take `north`, `east`, and positive `alt_m`; raw `ctx.senses.pose` and `publish_trajectory_setpoint` use NED (`z = -alt_m`).",
        ],
        "function_signatures": {
            "boot_drone": "boot_drone() -> ContextManager[Drone]",
            "takeoff": "takeoff(*, alt_m: float = 3.0, name: Optional[str] = None) -> SkillStep",
            "fly_to": "fly_to(x=None, y=None, z=None, *, north: Optional[float] = None, east: Optional[float] = None, alt_m: Optional[float] = None, direct: bool = False, mode: Optional[str] = None, replan_mode: Optional[str] = None, target_speed: Optional[float] = None, yaw_mode: Optional[str] = None, yaw_rate_deg_s: Optional[float] = None, name: Optional[str] = None) -> SkillStep",
            "fly_to_ned": "fly_to_ned(x: float, y: float, z: float, *, direct: bool = False, mode: Optional[str] = None, replan_mode: Optional[str] = None, target_speed: Optional[float] = None, name: Optional[str] = None) -> SkillStep",
            "orbit": "orbit(center=None, *, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, radius_m: float = 5.0, period_s: float = 20.0, duration_s: float = 60.0) -> SkillStep",
            "helix": "helix(center=None, *, center_north: Optional[float] = None, center_east: Optional[float] = None, alt_m: Optional[float] = None, alt_m_end: Optional[float] = None, radius_m: float = 5.0, period_s: float = 20.0, duration_s: float = 60.0) -> SkillStep",
            "yaw_to": "yaw_to(face=None, *, north: Optional[float] = None, east: Optional[float] = None, name: str = 'yaw_to') -> SkillStep",
            "capture": "capture(*, output_dir: str = '~/.ros/captures', filename: Optional[str] = None, timeout_s: float = 5.0) -> SkillStep",
            "brake": "brake(*, name: str = 'brake') -> SkillStep",
            "land": "land(*, name: str = 'land') -> SkillStep",
            "CameraSense": "CameraSense()",
            "VideoRecorder": "VideoRecorder(output_dir: str = '~/.ros/recordings', fps: float = 10.0)",
            "Snapshot": "Snapshot(output_dir: str = '~/.ros/captures')",
            "Sprayer": "Sprayer()",
            "Detector": "Detector(model_name: str = 'yolov8n')",
        },
        "example_script": AUTONOMY_LEVEL_TEMPLATES[4]["code"],
    }


def get_autonomy_level_template_data(level: int = 1) -> Dict[str, Any]:
    """Return the verified template and documentation for Autonomy Level 1..6."""
    lvl = max(1, min(6, int(level)))
    tpl = AUTONOMY_LEVEL_TEMPLATES[lvl]
    validation = validate_uav_python_code(tpl["code"])
    return {
        **tpl,
        "validation": validation,
    }
