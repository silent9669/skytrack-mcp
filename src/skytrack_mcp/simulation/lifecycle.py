"""Lifecycle management for the SkyTrack simulation and daemon Docker stacks."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.core.errors import SkyTrackError, SkyTrackErrorCode


def get_docker_services_status() -> Dict[str, Any]:
    """Check running state of all SkyTrack Docker containers."""
    res = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=skytrack", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    if res.returncode != 0:
        raise SkyTrackError(
            SkyTrackErrorCode.DOCKER_NOT_RUNNING,
            f"Failed to query Docker daemon: {res.stderr}",
            suggested_action="Ensure Docker Desktop is running on macOS",
        )

    containers: Dict[str, Any] = {}
    for line in res.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            name = parts[0]
            status = parts[1]
            ports = parts[2] if len(parts) > 2 else ""
            containers[name] = {
                "running": "Up" in status,
                "status": status,
                "ports": ports,
            }

    core_services = [
        "skytrack-deamon-gcs-backend-1",
        "skytrack-deamon-mavlink-bridge-1",
        "skytrack-simulation-gazebo-1",
        "skytrack-simulation-px4-1",
        "skytrack-simulation-mission-computer-1",
        "skytrack-simulation-skytrack-autonomy-1",
    ]
    all_ready = all(containers.get(c, {}).get("running", False) for c in core_services)

    return {
        "ready": all_ready,
        "containers": containers,
    }


def boot_simulation_environment(
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    spawn_pose: Optional[List[float]] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Configure docker compose files and launch simulation stack."""
    deamon_compose = client_data_dir / "docker" / "deamon" / "docker-compose.yml"
    sim_compose = client_data_dir / "docker" / "local-sim" / "docker-compose.yml"

    if not deamon_compose.exists() or not sim_compose.exists():
        raise SkyTrackError(
            SkyTrackErrorCode.SIMULATOR_NOT_READY,
            f"Docker compose files missing in {client_data_dir}",
            suggested_action="Check SkyTrack ClientData directory",
        )

    pose_str = (
        f"{spawn_pose[0]:.3f},{spawn_pose[1]:.3f},{spawn_pose[2]:.3f},0.000,0.000,0.000"
        if spawn_pose and len(spawn_pose) >= 3
        else "0.000,0.000,0.024,0.000,0.000,0.000"
    )

    # Configure local-sim compose
    sim_text = sim_compose.read_text(encoding="utf-8")
    sim_text = re.sub(r"GZ_WORLD:\s*.*", f"GZ_WORLD: {world}", sim_text)
    sim_text = re.sub(r"PX4_GZ_WORLD:\s*.*", f"PX4_GZ_WORLD: {world}", sim_text)
    sim_text = re.sub(r"PX4_SIM_MODEL:\s*.*", f"PX4_SIM_MODEL: {vehicle}", sim_text)
    sim_text = re.sub(r"PX4_GZ_MODEL_POSE:\s*.*", f"PX4_GZ_MODEL_POSE: {pose_str}", sim_text)
    sim_compose.write_text(sim_text, encoding="utf-8")

    env = {**os.environ, "APP_STORAGE_PATH": str(client_data_dir)}

    res_deamon = subprocess.run(
        ["docker", "compose", "-f", str(deamon_compose), "up", "-d"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    res_sim = subprocess.run(
        ["docker", "compose", "-f", str(sim_compose), "up", "-d"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    status = get_docker_services_status()
    return {
        "world": world,
        "vehicle": vehicle,
        "spawn_pose": pose_str,
        "deamon_status": "ok" if res_deamon.returncode == 0 else res_deamon.stderr,
        "simulation_status": "ok" if res_sim.returncode == 0 else res_sim.stderr,
        "services": status,
    }


def shutdown_simulation_environment(client_data_dir: Path = CLIENT_DATA_DIR) -> Dict[str, Any]:
    """Stop the simulation containers."""
    sim_compose = client_data_dir / "docker" / "local-sim" / "docker-compose.yml"
    env = {**os.environ, "APP_STORAGE_PATH": str(client_data_dir)}
    res = subprocess.run(
        ["docker", "compose", "-f", str(sim_compose), "stop"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "stopped": res.returncode == 0,
        "message": res.stdout or res.stderr,
    }
