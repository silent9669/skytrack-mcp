"""Pre-flight readiness must include observable MAVLink telemetry."""

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from skytrack_mcp.clients import docker_exec
from skytrack_mcp.diagnostics import healthcheck
from skytrack_mcp.mcp import tools


@pytest.mark.asyncio
async def test_ready_requires_connected_telemetry(monkeypatch):
    monkeypatch.setattr(healthcheck, "is_skytrack_running", lambda: True)
    monkeypatch.setattr(healthcheck, "get_cloud_auth_credentials", lambda: {"access_token": "test", "csrf_token": "test"})
    monkeypatch.setattr(healthcheck, "get_simulation_health", lambda: {"all_healthy": True})
    monkeypatch.setattr(healthcheck, "fetch_live_mavlink_telemetry", lambda: {"connected": False})
    monkeypatch.setattr(healthcheck, "CLIENT_DATA_DIR", Path(__file__).parent)

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    monkeypatch.setattr(healthcheck.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))

    report = await healthcheck.run_full_system_healthcheck()
    assert report["components"]["mavlink_telemetry_stream"] is False
    assert report["ready"] is False


def test_running_simulator_config_reads_container_world_and_vehicle(monkeypatch):
    def fake_inspect(args, **_):
        env = (["GZ_WORLD=warehouse"] if args[2] == docker_exec.GAZEBO_CONTAINER else [
            "PX4_GZ_WORLD=warehouse", "PX4_SIM_MODEL=x500_livox_mid_360",
        ])
        return subprocess.CompletedProcess(args, 0, json.dumps(env), "")

    monkeypatch.setattr(docker_exec, "_run_cmd", fake_inspect)

    assert docker_exec.get_simulation_runtime_config() == {
        "world": "warehouse", "vehicle": "x500_livox_mid_360",
    }


@pytest.mark.asyncio
async def test_context_does_not_call_recent_mission_the_active_app_selection(monkeypatch):
    monkeypatch.setattr(tools, "list_all_missions", lambda: [{
        "project_id": "P1", "mission_id": "M1",
        "world": {"name": "angiang"}, "vehicle": {"name": "x500_tennis_balls"},
    }])
    monkeypatch.setattr(tools, "get_simulation_health", lambda: {"all_healthy": False})
    monkeypatch.setattr(tools, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    context = await tools.tool_skytrack_get_context()

    assert context["mission_selection_source"] == "most_recent_modified"
    assert context["selected_world"] is None
    assert context["selected_vehicle"] is None
    assert context["active_mission"]["world"]["name"] == "angiang"


@pytest.mark.asyncio
async def test_context_preflight_uses_running_simulator_not_recent_mission(monkeypatch):
    monkeypatch.setattr(tools, "list_all_missions", lambda: [{
        "project_id": "P1", "mission_id": "M1",
        "world": "angiang", "vehicle": "x500_tennis_balls",
    }])
    monkeypatch.setattr(tools, "get_simulation_health", lambda: {"all_healthy": True})
    monkeypatch.setattr(tools, "fetch_live_mavlink_telemetry", lambda: {"connected": True})
    monkeypatch.setattr(tools, "get_simulation_runtime_config", lambda: {
        "world": "warehouse", "vehicle": "x500_livox_mid_360",
    }, raising=False)

    context = await tools.tool_skytrack_get_context()

    assert context["selected_world"] == "warehouse"
    assert context["selected_vehicle"] == "x500_livox_mid_360"
    assert context["active_mission"]["world"] == "angiang"
