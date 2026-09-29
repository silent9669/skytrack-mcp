"""A lost telemetry stream must not leave a mission waiting until RPC timeout."""

import pytest

from skytrack_mcp.simulation import observer


@pytest.mark.asyncio
async def test_observer_stops_after_persistent_telemetry_loss(monkeypatch):
    monkeypatch.setattr(observer, "fetch_live_mavlink_telemetry", lambda: {"connected": False})

    result = await observer.observe_simulation_execution(max_duration_s=0.2, poll_interval_s=0.001)

    assert result["completed"] is False
    assert "telemetry" in result["error"].lower()
    assert result["sample_count"] <= 3
