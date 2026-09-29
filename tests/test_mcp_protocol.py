"""Full MCP Wire Protocol Test: tools, resources, and prompts over stdio transport."""

from __future__ import annotations

import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_mcp_stdio_wire_protocol_full():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skytrack_mcp.server"],
    )

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # 1. Test Tools listing
        tools_res = await session.list_tools()
        tool_names = {t.name for t in tools_res.tools}

        required_groups = [
            # Environment
            "tool_skytrack_status",
            "tool_skytrack_get_version",
            # Projects/Missions
            "tool_skytrack_list_projects",
            "tool_skytrack_list_missions",
            "tool_skytrack_resolve_target",
            "tool_skytrack_check_permission",
            "tool_skytrack_open_mission",
            "tool_skytrack_get_mission",
            "tool_skytrack_validate_mission",
            # Worlds & Vehicles
            "tool_skytrack_list_worlds",
            "tool_skytrack_inspect_world",
            "tool_skytrack_list_vehicles",
            # UI Read-Only
            "tool_ui_get_state",
            # Composite Read-Only
            "inspect_world_map",
            "check_route_collisions",
            "get_uav_python_sdk_reference",
            "get_autonomy_level_template",
        ]
        for req in required_groups:
            assert req in tool_names, f"Expected tool '{req}' missing from server tool list."

        # Verify hazardous tools, un-gated mutators, live telemetry, and unsafe UI tools are excluded
        for forbidden in (
            "execute_route_mission",
            "execute_uav_python_script",
            "run_mission_and_wait_completion",
            "control_uav_flight",
            "tool_skytrack_simulation_start",
            "tool_skytrack_simulation_stop",
            "tool_skytrack_simulation_restart",
            "tool_skytrack_simulation_state",
            "tool_skytrack_simulation_observe",
            "manage_simulation_stack",
            "tool_skytrack_recover",
            "tool_skytrack_get_context",
            "tool_skytrack_healthcheck",
            "tool_skytrack_diagnostics",
            "tool_ui_click",
            "tool_ui_type",
            "tool_ui_key",
            "tool_ui_snapshot",
            "tool_skytrack_create_mission",
            "tool_skytrack_clone_mission",
            "tool_skytrack_import_mission",
            "tool_skytrack_patch_mission",
            "tool_skytrack_set_mission",
            "tool_skytrack_save_mission",
            "draw_route_on_map",
            "plan_coverage_route",
            "convert_route_to_python_script",
            "write_and_save_uav_script",
            "get_uav_telemetry",
            "harvest_flight_report",
        ):
            assert forbidden not in tool_names, f"Prohibited tool '{forbidden}' must not be registered."

        # 2. Test Tool Call: tool_skytrack_status
        status_res = await session.call_tool("tool_skytrack_status", {})
        assert not getattr(status_res, "is_error", False)
        assert any("simulation_execution" in str(c) for c in status_res.content)

        # 2b. Test Tool Call: tool_skytrack_resolve_target (missing query should return MISSING or fail-closed UNAVAILABLE cleanly)
        resolve_res = await session.call_tool("tool_skytrack_resolve_target", {})
        assert not getattr(resolve_res, "is_error", False)
        assert any("MISSING" in str(c) or "UNAVAILABLE" in str(c) for c in resolve_res.content)

        # 2c. Test Tool Call: tool_skytrack_check_permission
        perm_res = await session.call_tool(
            "tool_skytrack_check_permission",
            {"project_id": "01M3PRJTEST00000000000000"},
        )
        assert not getattr(perm_res, "is_error", False)
        assert any("edit_authorization" in str(c) for c in perm_res.content)

        # 3. Test Tool Call: inspect_world_map (reads packaged worlds/warehouse.sdf)
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
