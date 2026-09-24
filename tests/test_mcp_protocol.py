"""Test the SkyTrack MCP Server over the real MCP stdio JSON-RPC wire protocol."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_wire_protocol():
    server_bin = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "skytrack-mcp"
    params = StdioServerParameters(
        command=str(server_bin),
        args=[],
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = {t.name for t in tools_result.tools}

            expected_tools = {
                "list_missions_and_worlds",
                "get_mission_state",
                "inspect_world_map",
                "check_route_collisions",
                "get_uav_telemetry",
                "plan_coverage_route",
                "draw_route_on_map",
                "execute_route_mission",
                "control_uav_flight",
                "get_uav_python_sdk_reference",
                "convert_route_to_python_script",
                "write_and_save_uav_script",
                "execute_uav_python_script",
                "stop_uav_python_script",
                "get_uav_script_logs",
            }
            assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

            # Call inspect_world_map over MCP wire protocol
            call_res = await session.call_tool(
                "inspect_world_map",
                {"world_name": "warehouse", "slice_altitude_m": 2.5, "grid_half_size_m": 10.0},
            )
            assert not getattr(call_res, "is_error", False)
            assert any("warehouse" in str(c) for c in call_res.content)

            # Call get_uav_telemetry over MCP wire protocol
            telem_res = await session.call_tool("get_uav_telemetry", {})
            assert not getattr(telem_res, "is_error", False)
            assert any("landed_state" in str(c) for c in telem_res.content)
