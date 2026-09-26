"""Route geometry, coverage planning, and collision checks."""

from skytrack_mcp.route.coverage import plan_boustrophedon_coverage
from skytrack_mcp.route.geometry_utils import (
    compute_route_metrics,
    distance_2d,
    distance_3d,
    verify_route_collision_freedom,
)

__all__ = [
    "distance_2d",
    "distance_3d",
    "compute_route_metrics",
    "verify_route_collision_freedom",
    "plan_boustrophedon_coverage",
]
