"""3D Geometry calculations, Rotated Axis-Aligned Bounding Boxes (AABB), and ray/box intersections."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple


def parse_pose(pose_str: str | None) -> Tuple[float, float, float, float, float, float]:
    """Parse 'x y z roll pitch yaw' string into a 6-float tuple."""
    if not pose_str:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    parts = [float(p) for p in pose_str.strip().split()[:6]]
    while len(parts) < 6:
        parts.append(0.0)
    return (parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])


def compose_pose_2d(
    parent: Tuple[float, float, float, float, float, float],
    child: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float, float, float, float, float]:
    """Compose parent and child poses (with yaw rotation)."""
    px, py, pz, pr, pp, pyaw = parent
    cx, cy, cz, cr, cp, cyaw = child
    cos_y = math.cos(pyaw)
    sin_y = math.sin(pyaw)
    wx = px + cx * cos_y - cy * sin_y
    wy = py + cx * sin_y + cy * cos_y
    wz = pz + cz
    return (wx, wy, wz, pr + cr, pp + cp, pyaw + cyaw)


def compute_rotated_aabb(
    cx: float,
    cy: float,
    cz: float,
    sx: float,
    sy: float,
    sz: float,
    yaw: float,
) -> Dict[str, float]:
    """Compute Axis-Aligned Bounding Box (AABB) bounds of an oriented bounding box."""
    cos_y = abs(math.cos(yaw))
    sin_y = abs(math.sin(yaw))
    ext_x = (sx * cos_y + sy * sin_y) / 2.0
    ext_y = (sx * sin_y + sy * cos_y) / 2.0
    ext_z = sz / 2.0
    return {
        "min_x": round(cx - ext_x, 3),
        "max_x": round(cx + ext_x, 3),
        "min_y": round(cy - ext_y, 3),
        "max_y": round(cy + ext_y, 3),
        "min_z": round(cz - ext_z, 3),
        "max_z": round(cz + ext_z, 3),
    }


def segment_intersects_aabb(
    p0: Tuple[float, float, float] | List[float],
    p1: Tuple[float, float, float] | List[float],
    aabb: Dict[str, float],
    clearance: float = 0.35,
) -> bool:
    """Slab method 3D line segment vs inflated AABB intersection test."""
    bounds = [
        (aabb["min_x"] - clearance, aabb["max_x"] + clearance),
        (aabb["min_y"] - clearance, aabb["max_y"] + clearance),
        (aabb["min_z"] - clearance, aabb["max_z"] + clearance),
    ]
    t_min = 0.0
    t_max = 1.0
    for i in range(3):
        d = p1[i] - p0[i]
        b_min, b_max = bounds[i]
        if abs(d) < 1e-9:
            if p0[i] < b_min or p0[i] > b_max:
                return False
        else:
            inv_d = 1.0 / d
            t1 = (b_min - p0[i]) * inv_d
            t2 = (b_max - p0[i]) * inv_d
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return False
    return True
