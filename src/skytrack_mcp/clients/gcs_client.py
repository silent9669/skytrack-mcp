"""Async HTTP & WebSocket client for SkyTrack GCS Backend (:20002) and Path Planner API (:20007)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional

import httpx
import websockets

from skytrack_mcp.config import GCS_BACKEND_URL, GCS_FEEDBACK_WS_URL, PATH_PLANNER_URL


class SkyTrackGCSClient:
    """Client for UAV Control API (:20002) and Skytrack Path Planner API (:20007)."""

    def __init__(
        self,
        gcs_url: str = GCS_BACKEND_URL,
        planner_url: str = PATH_PLANNER_URL,
        ws_url: str = GCS_FEEDBACK_WS_URL,
    ) -> None:
        self.gcs_url = gcs_url.rstrip("/")
        self.planner_url = planner_url.rstrip("/")
        self.ws_url = ws_url

    async def get_planner_health(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.planner_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def get_gcs_feedback_snapshot(self) -> Dict[str, Any]:
        """Connect briefly to ws://127.0.0.1:20002/ws/feedback to get action feedback."""
        try:
            async with websockets.connect(self.ws_url) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                return json.loads(msg)
        except Exception as exc:
            return {"error": str(exc)}

    async def plan_coverage_xy(
        self,
        area_coords: List[Dict[str, float]],
        spacing: float = 2.0,
        orientation: float = 90.0,
        hole_coords: Optional[List[List[Dict[str, float]]]] = None,
        padding: float = 0.0,
        safety: float = 0.5,
        plan_only: bool = False,
    ) -> Dict[str, Any]:
        """Call POST :20007/plan-coverage-xy to compute an optimized zigzag coverage route."""
        payload: Dict[str, Any] = {
            "area_coords": [{"x": float(p["x"]), "y": float(p["y"])} for p in area_coords],
            "spacing": float(spacing),
            "orientation": float(orientation),
            "padding": float(padding),
            "safety": float(safety),
            "plan_only": bool(plan_only),
        }
        if hole_coords:
            payload["hole_coords"] = [
                [{"x": float(p["x"]), "y": float(p["y"])} for p in hole]
                for hole in hole_coords
            ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.planner_url}/plan-coverage-xy", json=payload)
            if resp.status_code >= 400:
                raise ValueError(f"Path Planner error ({resp.status_code}): {resp.text}")
            return resp.json()

    async def split_waypoints_nfz(
        self,
        waypoints_enu: List[List[float]],
        nfz_zones: List[Dict[str, Any]],
        boundary_margin_m: float = 1.0,
    ) -> Dict[str, Any]:
        """Call POST :20007/split-waypoints-nfz to split coverage legs around No-Fly Zones."""
        wp_items = []
        for idx, pt in enumerate(waypoints_enu):
            wp_items.append(
                {
                    "point": [float(pt[0]), float(pt[1]), float(pt[2])],
                    "mode": None if idx == 0 else "coverage",
                    "is_inside_nfz": False,
                }
            )
        payload = {
            "waypoints": wp_items,
            "nfz": {"zones": nfz_zones},
            "boundary_margin_m": float(boundary_margin_m),
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.planner_url}/split-waypoints-nfz", json=payload)
            if resp.status_code >= 400:
                raise ValueError(f"NFZ Split error ({resp.status_code}): {resp.text}")
            return resp.json()

    async def execute_mission_v2(
        self,
        waypoints: List[Dict[str, Any]],
        takeoff_altitude: float = 2.0,
        target_speed: float = 2.0,
        avoidance_mode: str = "avoid",
        smart: bool = True,
        no_fly_zones: Optional[List[Dict[str, Any]]] = None,
        end_action: Optional[str] = "rtl",
    ) -> Dict[str, Any]:
        """Build a canonical FrontendMissionExecutionRequest and POST to :20002/mission/v2/execute."""
        actions: List[Dict[str, Any]] = []
        for wp in waypoints:
            wp_type = wp.get("type", "navigation")
            if wp_type in ("navigate", "navigation", "waypoint") or ("x" in wp and "y" in wp):
                if "data" in wp and isinstance(wp["data"], list) and len(wp["data"]) == 3:
                    x, y, z = float(wp["data"][0]), float(wp["data"][1]), float(wp["data"][2])
                else:
                    x = float(wp.get("x", 0.0))
                    y = float(wp.get("y", 0.0))
                    z = float(wp.get("z", takeoff_altitude))
                actions.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "navigation",
                        "frame": wp.get("frame", "enu"),
                        "x": x,
                        "y": y,
                        "z": z,
                        "target_speed": float(wp.get("target_speed", target_speed)),
                    }
                )
                after = wp.get("after_action")
                if after in ("drop-ball", "drop_payload"):
                    actions.append({"id": str(uuid.uuid4()), "type": "drop_payload"})
                elif after in ("take-photo", "snapshot"):
                    actions.append(
                        {"id": str(uuid.uuid4()), "type": "camera_trigger", "operation": "snapshot"}
                    )
                elif after in ("start-recording-video", "recording_on"):
                    actions.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "camera_trigger",
                            "operation": "recording_on",
                        }
                    )
                elif after in ("stop-recording-video", "recording_off"):
                    actions.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "camera_trigger",
                            "operation": "recording_off",
                        }
                    )
            elif wp_type in ("drop-ball", "drop_payload"):
                actions.append({"id": str(uuid.uuid4()), "type": "drop_payload"})
            elif wp_type in ("rtl", "land"):
                actions.append({"id": str(uuid.uuid4()), "type": wp_type})
            elif wp_type in ("camera_trigger", "spray", "break", "ai_detect"):
                action_copy = dict(wp)
                action_copy["id"] = str(uuid.uuid4())
                actions.append(action_copy)

        if end_action in ("rtl", "land"):
            if not actions or actions[-1].get("type") not in ("rtl", "land"):
                actions.append({"id": str(uuid.uuid4()), "type": end_action})

        av_mode = avoidance_mode.lower()
        if av_mode not in ("avoid", "brake"):
            av_mode = "avoid"

        payload = {
            "actions": actions,
            "settings": {
                "takeoff_altitude": max(1.0, float(takeoff_altitude)),
                "avoidance_mode": av_mode,
                "smart": bool(smart),
                "no_fly_zones": no_fly_zones or [],
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.gcs_url}/mission/v2/execute", json=payload)
            return {
                "status_code": resp.status_code,
                "ok": resp.status_code < 400,
                "response": resp.json() if resp.content else {},
                "submitted_payload": payload,
            }

    async def control_flight_or_mission(
        self,
        command: str,
        altitude_m: float = 2.5,
        smart: bool = True,
    ) -> Dict[str, Any]:
        """Dispatch flight or mission control commands to :20002."""
        cmd = command.lower().strip()
        endpoint_map = {
            "takeoff": ("/flight/v2/takeoff", {"takeoff_altitude": max(1.0, min(50.0, float(altitude_m)))}),
            "land": ("/flight/v2/land", {"smart_land": bool(smart), "timeout_sec": 60}),
            "rtl": ("/flight/v2/rtl", {"smart_rtl": bool(smart), "timeout_sec": 300}),
            "pause_mission": ("/mission/v2/pause", None),
            "resume_mission": ("/mission/v2/resume", None),
            "cancel_mission": ("/mission/v2/cancel", None),
            "smart_land": ("/mission/smartland", None),
        }
        if cmd not in endpoint_map:
            raise ValueError(f"Unsupported command '{command}'. Valid: {list(endpoint_map.keys())}")

        path, body = endpoint_map[cmd]
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"{self.gcs_url}{path}", json=body)
            return {
                "command": cmd,
                "endpoint": path,
                "status_code": resp.status_code,
                "ok": resp.status_code < 400,
                "response": resp.json() if resp.content else {},
            }

    async def configure_world_and_avoidance(
        self,
        world_name: Optional[str] = None,
        avoidance_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call /set_world_name and/or /set_avoidance_mode on :20002."""
        results: Dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=15.0) as client:
            if world_name:
                r1 = await client.post(
                    f"{self.gcs_url}/set_world_name",
                    json={"world_name": world_name},
                )
                results["set_world_name"] = {
                    "status_code": r1.status_code,
                    "response": r1.json() if r1.content else {},
                }
            if avoidance_mode:
                mode_upper = avoidance_mode.upper()
                if mode_upper not in ("BRAKE", "AVOID", "OFF"):
                    raise ValueError("avoidance_mode must be one of: AVOID, BRAKE, OFF")
                r2 = await client.post(
                    f"{self.gcs_url}/set_avoidance_mode",
                    json={"avoidance_mode": mode_upper},
                )
                results["set_avoidance_mode"] = {
                    "status_code": r2.status_code,
                    "response": r2.json() if r2.content else {},
                }
        return results
