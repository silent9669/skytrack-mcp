"""Coverage path planner integrating with SkyTrack Path Planner API (:20007)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from skytrack_mcp.config import PATH_PLANNER_URL
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode


async def plan_boustrophedon_coverage(
    area_coords: List[Dict[str, float]],
    spacing_m: float = 2.0,
    orientation_deg: float = 90.0,
    altitude_m: float = 2.5,
    hole_coords: Optional[List[List[Dict[str, float]]]] = None,
    no_fly_zones: Optional[List[Dict[str, Any]]] = None,
    planner_url: str = PATH_PLANNER_URL,
) -> Dict[str, Any]:
    """Compute optimal coverage path via :20007/plan-coverage-xy and optional NFZ split."""
    if len(area_coords) < 3:
        raise SkyTrackError(
            SkyTrackErrorCode.MISSION_INVALID,
            "Coverage area must have at least 3 polygon vertices.",
        )

    payload: Dict[str, Any] = {
        "area_coords": [{"x": float(p["x"]), "y": float(p["y"])} for p in area_coords],
        "spacing": float(spacing_m),
        "orientation": float(orientation_deg),
        "padding": 0.0,
        "safety": 0.5,
        "plan_only": False,
    }
    if hole_coords:
        payload["hole_coords"] = [
            [{"x": float(p["x"]), "y": float(p["y"])} for p in hole] for hole in hole_coords
        ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{planner_url}/plan-coverage-xy", json=payload)
            resp.raise_for_status()
            plan_res = resp.json()
        except Exception as exc:
            raise SkyTrackError(
                SkyTrackErrorCode.INTERNAL_ERROR,
                f"Path Planner API (:20007) request failed: {exc}",
                suggested_action="Verify skytrack-deamon-gcs-backend-1 is running on port 20007",
            )

    vertices = plan_res.get("vertexs", [])
    waypoints_3d: List[List[float]] = [
        [round(float(v["x"]), 3), round(float(v["y"]), 3), round(float(altitude_m), 3)]
        for v in vertices
    ]

    nfz_summary = None
    if no_fly_zones and waypoints_3d:
        wp_items = []
        for idx, pt in enumerate(waypoints_3d):
            wp_items.append(
                {
                    "point": [float(pt[0]), float(pt[1]), float(pt[2])],
                    "mode": None if idx == 0 else "coverage",
                    "is_inside_nfz": False,
                }
            )
        nfz_payload = {
            "waypoints": wp_items,
            "nfz": {"zones": no_fly_zones},
            "boundary_margin_m": 1.0,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                split_resp = await client.post(f"{planner_url}/split-waypoints-nfz", json=nfz_payload)
                split_resp.raise_for_status()
                nfz_res = split_resp.json()
                waypoints_3d = [wp["point"] for wp in nfz_res.get("waypoints", [])]
                nfz_summary = {
                    "zone_count": nfz_res.get("zone_count"),
                    "legs_inside_nfz": nfz_res.get("legs_inside_nfz"),
                }
            except Exception as exc:
                raise SkyTrackError(
                    SkyTrackErrorCode.INTERNAL_ERROR,
                    f"NFZ Split API (:20007) failed: {exc}",
                )

    return {
        "waypoint_count": len(waypoints_3d),
        "waypoints": waypoints_3d,
        "nfz_split_summary": nfz_summary,
        "spacing_m": spacing_m,
        "orientation_deg": orientation_deg,
        "altitude_m": altitude_m,
    }
