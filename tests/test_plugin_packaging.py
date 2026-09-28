import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"


def test_plugin_manifest_is_valid_and_portable() -> None:
    plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))

    assert plugin["name"] == "skytrack"
    assert plugin["version"] == "0.2.0"
    assert (
        plugin["description"]
        == "Cross-platform SkyTrack Mission Studio MCP & Autonomous Flight Engineering Skill for Claude Code"
    )
    assert "./.claude/skills/skytrack/" in plugin["skills"]

    server = plugin["mcpServers"]["skytrack"]
    assert server["command"] == "uv"
    assert server["args"] == ["run", "skytrack-mcp"]
    assert server["env"]["UV_PROJECT"] == "${CLAUDE_PLUGIN_ROOT}"
    assert "hooks" not in plugin

    for config_path in (ROOT / ".mcp.json", PLUGIN_MANIFEST):
        assert "/Users/" not in config_path.read_text(encoding="utf-8")


def test_project_version_is_020() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', pyproject)

    assert match is not None
    assert match.group(1) == "0.2.0"


def test_skill_docs_match_v020_workflow() -> None:
    docs = {
        "dispatcher": (ROOT / ".claude/skills/skytrack/SKILL.md").read_text(encoding="utf-8"),
        "operator": (ROOT / "skills/skytrack-operator/SKILL.md").read_text(encoding="utf-8"),
        "authoring": (ROOT / "skills/skytrack-mission-authoring/SKILL.md").read_text(encoding="utf-8"),
    }
    all_docs = "\n".join(docs.values()).lower()

    required_phrases = (
        "naturally discoverable",
        "/skytrack",
        "tool_skytrack_resolve_target",
        "project and mission names or ids",
        "ask the user before creating",
        "tool_skytrack_check_permission",
        "edit_authorization",
        "view-only",
        "immutable",
        "judge",
        "plan mode",
        "code mode",
        "dynamic perception",
        "transactional",
        "tool_skytrack_save_mission",
        "read-back",
        "preserve the inactive",
        "user runs every simulation in skytrack desktop",
        "local docker or cloud",
        "never dispatch",
        "hãy debug",
        "latest run/report for that exact mission",
        "user-provided logs",
        "same mission",
        "rerun in skytrack desktop",
    )
    for phrase in required_phrases:
        assert phrase in all_docs, f"Missing workflow guidance: {phrase}"

    assert "tool_skytrack_resolve_target" in docs["dispatcher"].lower()
    assert "tool_skytrack_check_permission" in docs["operator"].lower()
    assert "preserve the inactive" in docs["authoring"].lower()
