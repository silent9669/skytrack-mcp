"""Geometry utilities for route length, distance, clearance checks, and collision detection."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from skytrack_mcp.world.geometry import segment_intersects_aabb
from skytrack_mcp.world.sdf_parser import parse_world_sdf


def distance_2d(p0: Tuple[float, float] | List[float], p1: Tuple[float, float] | List[float]) -> float:
    return math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2)


def distance_3d(
    p0: Tuple[float, float, float] | List[float], p1: Tuple[float, float, float] | List[float]
) -> float:
    return math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2)


def compute_route_metrics(waypoints: List[List[float]]) -> Dict[str, float]:
    """Calculate total 3D distance, 2D planar distance, max altitude, and min altitude."""
    if not waypoints:
        return {"total_distance_m": 0.0, "planar_distance_m": 0.0, "max_alt_m": 0.0, "min_alt_m": 0.0}

    total_3d = 0.0
    total_2d = 0.0
    alts = [float(p[2]) for p in waypoints if len(p) >= 3]

    for idx in range(len(waypoints) - 1):
        p0 = waypoints[idx]
        p1 = waypoints[idx + 1]
        total_3d += distance_3d(p0, p1)
        total_2d += distance_2d(p0[:2], p1[:2])

    return {
        "total_distance_m": round(total_3d, 2),
        "planar_distance_m": round(total_2d, 2),
        "max_alt_m": round(max(alts), 2) if alts else 0.0,
        "min_alt_m": round(min(alts), 2) if alts else 0.0,
    }


def verify_route_collision_freedom(
    world_name: str,
    waypoints: List[List[float]],
    clearance_m: float = 0.4,
) -> Dict[str, Any]:
    """Check a 3D waypoint path against all 3D obstacles in a Gazebo world."""
    world_info = parse_world_sdf(world_name)
    obstacles = world_info["obstacles"]
    conflicts: List[Dict[str, Any]] = []

    for idx in range(len(waypoints) - 1):
        p0 = [float(v) for v in waypoints[idx][:3]]
        p1 = [float(v) for v in waypoints[idx + 1][:3]]
        for obs in obstacles:
            if segment_intersects_aabb(p0, p1, obs["aabb"], clearance=clearance_m):
                conflicts.append(
                    {
                        "leg_index": idx,
                        "from": p0,
                        "to": p1,
                        "obstacle_model": obs["model"],
                        "obstacle_collision": obs["collision"],
                        "obstacle_aabb": obs["aabb"],
                    }
                )

    metrics = compute_route_metrics(waypoints)

    return {
        "world": world_name,
        "is_collision_free": len(conflicts) == 0,
        "clearance_m": clearance_m,
        "legs_checked": max(0, len(waypoints) - 1),
        "metrics": metrics,
        "conflicts": conflicts,
    }
