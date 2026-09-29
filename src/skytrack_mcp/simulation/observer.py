"""Continuous simulation observation, telemetry sampling, and state transition tracking."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from skytrack_mcp.clients.docker_exec import fetch_live_mavlink_telemetry


async def observe_simulation_execution(
    max_duration_s: float = 120.0,
    poll_interval_s: float = 3.0,
    on_sample: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Observe active UAV flight until landed safely or timeout."""
    start_time = time.time()
    samples: List[Dict[str, Any]] = []
    airborne_detected = False
    landed_after_airborne = False
    battery_depleted = False
    last_error: Optional[str] = None
    disconnected_samples = 0

    while (time.time() - start_time) < max_duration_s:
        await asyncio.sleep(poll_interval_s)
        tel = fetch_live_mavlink_telemetry()

        elapsed = round(time.time() - start_time, 1)
        state = tel.get("landed_state")
        battery = tel.get("battery_percentage")
        mode = tel.get("flight_mode")

        sample = {
            "elapsed_s": elapsed,
            "connected": tel.get("connected"),
            "landed_state": state,
            "flight_mode": mode,
            "battery_pct": battery,
            "local_enu": tel.get("local_enu_m"),
            "armed": tel.get("is_armed"),
        }
        samples.append(sample)

        if on_sample:
            try:
                on_sample(sample)
            except Exception:
                pass

        disconnected_samples = disconnected_samples + 1 if not tel.get("connected") else 0
        if disconnected_samples >= 3:
            last_error = "MAVLink telemetry disconnected during mission observation"
            break

        if state in ("IN_AIR", "TAKEOFF", "LANDING"):
            airborne_detected = True

        if airborne_detected and state == "ON_GROUND":
            landed_after_airborne = True
            break

        if battery is not None and battery <= 10.0:
            battery_depleted = True
            last_error = f"Battery critically low ({battery}%) during flight"
            break

    total_time = round(time.time() - start_time, 1)

    return {
        "completed": landed_after_airborne,
        "airborne_detected": airborne_detected,
        "landed_safely": landed_after_airborne,
        "battery_depleted": battery_depleted,
        "timeout": (total_time >= max_duration_s) and not landed_after_airborne,
        "total_duration_s": total_time,
        "sample_count": len(samples),
        "final_sample": samples[-1] if samples else None,
        "samples": samples,
        "error": last_error,
    }
