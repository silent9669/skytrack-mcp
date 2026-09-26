"""Full MCP Wire Protocol Test: tools, resources, and prompts over stdio transport."""

from __future__ import annotations

from pathlib import Path
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_wire_protocol_full():
    server_bin = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "skytrack-mcp"
    params = StdioServerParameters(command=str(server_bin), args=[])

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 1. Test Tools listing
            tools_res = await session.list_tools()
            tool_names = {t.name for t in tools_res.tools}

            required_groups = [
                # Environment
                "tool_skytrack_status",
                "tool_skytrack_get_context",
                "tool_skytrack_healthcheck",
                # Projects/Missions
                "tool_skytrack_list_projects",
                "tool_skytrack_list_missions",
                "tool_skytrack_get_mission",
                "tool_skytrack_validate_mission",
                "tool_skytrack_patch_mission",
                # Worlds & Vehicles
                "tool_skytrack_list_worlds",
                "tool_skytrack_inspect_world",
                "tool_skytrack_list_vehicles",
                # UI & Simulation
                "tool_ui_snapshot",
                "tool_skytrack_simulation_state",
                # Reports & Diagnostics
                "tool_skytrack_report_read",
                "tool_skytrack_diagnostics",
                # Composite
                "list_missions_and_worlds",
                "inspect_world_map",
                "check_route_collisions",
                "get_uav_telemetry",
                "plan_coverage_route",
                "draw_route_on_map",
                "convert_route_to_python_script",
                "write_and_save_uav_script",
                "execute_uav_python_script",
            ]
            for req in required_groups:
                assert req in tool_names, f"Expected tool '{req}' missing from server tool list."

            # 2. Test Tool Call: tool_skytrack_get_context
            ctx_res = await session.call_tool("tool_skytrack_get_context", {})
            assert not getattr(ctx_res, "is_error", False)
            assert any("selected_world" in str(c) for c in ctx_res.content)

            # 3. Test Tool Call: inspect_world_map
            map_res = await session.call_tool(
                "inspect_world_map",
                {"world_name": "warehouse", "slice_altitude_m": 2.5, "grid_half_size_m": 10.0},
            )
            assert not getattr(map_res, "is_error", False)
            assert any("warehouse" in str(c) for c in map_res.content)

            # 4. Test Resources listing and reading
            res_list = await session.list_resources()
            res_uris = {str(r.uri) for r in res_list.resources}
            assert "skytrack://docs/operator-guide" in res_uris
            assert "skytrack://schema/mission" in res_uris
            assert "skytrack://worlds" in res_uris
            assert "skytrack://capabilities" in res_uris

            guide_read = await session.read_resource("skytrack://docs/operator-guide")
            assert "SkyTrack Mission Studio" in str(guide_read.contents[0])

            # 5. Test Prompts listing and getting
            prompt_list = await session.list_prompts()
            prompt_names = {p.name for p in prompt_list.prompts}
            assert "skytrack_solve_mission" in prompt_names
            assert "skytrack_inspect_world_prompt" in prompt_names

            solve_p = await session.get_prompt(
                "skytrack_solve_mission",
                {"assignment": "Inspect warehouse aisles and drop balls"},
            )
            assert "Inspect warehouse aisles" in str(solve_p.messages[0].content)
