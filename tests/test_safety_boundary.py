"""Unit test ensuring the default SkyTrack MCP server excludes all hazardous tools,
un-gated mutators, live telemetry pollers, container diagnosticians, and unsafe UI controls.

Under the 2026-09-28 approved specification for Phase 1 (Read-Only Core):
The default distributed MCP server must strictly expose the exact 22 read-only inspection/validation tools.
"""

from __future__ import annotations

import re

import pytest

from skytrack_mcp.mcp.prompts import get_prompt_templates
from skytrack_mcp.server import mcp

PROHIBITED_TOOLS = {
    # Live flight execution
    "execute_route_mission",
    "execute_uav_python_script",
    "run_mission_and_wait_completion",
    "stop_uav_python_script",
    # UAV flight control
    "control_uav_flight",
    # Simulation stack lifecycle & live observation / diagnostics
    "tool_skytrack_simulation_start",
    "tool_skytrack_simulation_stop",
    "tool_skytrack_simulation_restart",
    "tool_skytrack_simulation_state",
    "tool_skytrack_simulation_observe",
    "manage_simulation_stack",
    "get_uav_telemetry",
    "get_uav_script_logs",
    "tool_skytrack_logs",
    "tool_skytrack_docker_status",
    "tool_skytrack_healthcheck",
    "tool_skytrack_diagnostics",
    "tool_skytrack_get_context",
    "list_missions_and_worlds",
    # Automated recovery
    "tool_skytrack_recover",
    # Unsafe UI interaction & process side effects
    "tool_skytrack_launch",
    "tool_skytrack_focus",
    "tool_ui_click",
    "tool_ui_type",
    "tool_ui_key",
    "tool_ui_snapshot",
    "tool_skytrack_capture_world",
    # Un-gated mutators & disk exporters
    "tool_skytrack_create_mission",
    "tool_skytrack_clone_mission",
    "tool_skytrack_export_mission",
    "tool_skytrack_import_mission",
    "tool_skytrack_patch_mission",
    "tool_skytrack_set_mission",
    "tool_skytrack_save_mission",
    "tool_skytrack_select_world",
    "tool_skytrack_select_vehicle",
    "tool_skytrack_report_export",
    "tool_skytrack_report_read",
    "tool_skytrack_verify_mission_requirements",
    "harvest_flight_report",
    "draw_route_on_map",
    "plan_coverage_route",
    "convert_route_to_python_script",
    "write_and_save_uav_script",
    "create_mission_on_cloud",
    "sync_mission_to_cloud",
}

EXPECTED_READ_ONLY_TOOLS = {
    "tool_skytrack_status",
    "tool_skytrack_get_version",
    "tool_skytrack_list_projects",
    "tool_skytrack_list_missions",
    "tool_skytrack_resolve_target",
    "tool_skytrack_check_permission",
    "tool_skytrack_open_mission",
    "tool_skytrack_get_mission",
    "tool_skytrack_get_mission_json",
    "tool_skytrack_validate_mission",
    "tool_skytrack_list_worlds",
    "tool_skytrack_get_world_context",
    "tool_skytrack_inspect_world",
    "tool_skytrack_list_vehicles",
    "tool_skytrack_get_vehicle_context",
    "tool_ui_get_state",
    "get_mission_state",
    "inspect_world_map",
    "check_route_collisions",
    "get_uav_python_sdk_reference",
    "get_autonomy_level_template",
    "list_skytrack_cloud_projects",
    "tool_skytrack_author_plan",
    "tool_skytrack_author_code",
    "tool_skytrack_switch_mode",
    "tool_skytrack_debug_mission",
    "tool_skytrack_evaluate_semifinal_2026",
}


@pytest.mark.asyncio
async def test_prohibited_tools_not_registered():
    """Verify none of the prohibited tools are in the FastMCP tool list."""
    registered_tools = {tool.name for tool in await mcp.list_tools()}
    found_prohibited = registered_tools.intersection(PROHIBITED_TOOLS)
    assert not found_prohibited, (
        f"Prohibited tools registered in default MCP server: {found_prohibited}"
    )


@pytest.mark.asyncio
async def test_exact_read_only_tool_inventory():
    """Verify the default server exposes the exact 22-tool read-only toolset."""
    registered_tools = {tool.name for tool in await mcp.list_tools()}
    assert registered_tools == EXPECTED_READ_ONLY_TOOLS, (
        f"Tool inventory mismatch.\n"
        f"Unexpected extra tools: {registered_tools - EXPECTED_READ_ONLY_TOOLS}\n"
        f"Missing tools: {EXPECTED_READ_ONLY_TOOLS - registered_tools}"
    )


def test_prompt_templates_reference_only_registered_tools():
    """Verify that every tool mentioned in active prompt templates is currently registered."""
    tool_regex = re.compile(r"`([a-zA-Z0-9_]+)`")
    templates = get_prompt_templates()

    for p_name, p_data in templates.items():
        template_text = p_data.get("template", "")
        referenced = set(tool_regex.findall(template_text))
        for ref in referenced:
            if ref.startswith("tool_") or ref in EXPECTED_READ_ONLY_TOOLS:
                assert ref in EXPECTED_READ_ONLY_TOOLS, (
                    f"Prompt '{p_name}' references unregistered tool '{ref}'."
                )
