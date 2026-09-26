"""Generates 2D top-down ASCII obstacle occupancy slices at flight altitudes."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_occupancy_grid_2d(
    obstacles: List[Dict[str, Any]],
    slice_altitude_m: float = 2.5,
    grid_half_size_m: float = 15.0,
    grid_resolution: int = 31,
) -> Dict[str, Any]:
    """Render a 2D top-down ASCII occupancy slice from 3D obstacle bounding boxes."""
    slice_obstacles = [
        obs
        for obs in obstacles
        if obs["aabb"]["min_z"] <= slice_altitude_m <= obs["aabb"]["max_z"]
    ]

    n = max(11, min(61, grid_resolution))
    step = (2.0 * grid_half_size_m) / (n - 1)
    grid_lines: List[str] = []
    header = (
        f"Top-Down Map Slice at z={slice_altitude_m:.2f}m | "
        f"X (East): [{-grid_half_size_m:.1f}m .. +{grid_half_size_m:.1f}m], "
        f"Y (North): [+{grid_half_size_m:.1f}m .. {-grid_half_size_m:.1f}m] | "
        f"'#'=Obstacle, 'S'=Origin(0,0), '.'=Free"
    )
    grid_lines.append(header)

    for row in range(n):
        y_val = grid_half_size_m - row * step
        row_chars: List[str] = []
        for col in range(n):
            x_val = -grid_half_size_m + col * step
            if abs(x_val) < step * 0.55 and abs(y_val) < step * 0.55:
                row_chars.append("S")
                continue
            hit = False
            for obs in slice_obstacles:
                b = obs["aabb"]
                if b["min_x"] <= x_val <= b["max_x"] and b["min_y"] <= y_val <= b["max_y"]:
                    hit = True
                    break
            row_chars.append("#" if hit else ".")
        grid_lines.append(f"Y={y_val:+6.1f}m | {''.join(row_chars)}")

    return {
        "slice_altitude_m": slice_altitude_m,
        "grid_half_size_m": grid_half_size_m,
        "obstacles_at_slice": len(slice_obstacles),
        "ascii_map_2d": "\n".join(grid_lines),
    }
