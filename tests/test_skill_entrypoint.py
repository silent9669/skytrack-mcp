"""Checks that the public SkyTrack command is discoverable in Claude Code."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_single_public_skytrack_skill_is_discoverable() -> None:
    skill = PROJECT_ROOT / ".claude" / "skills" / "skytrack" / "SKILL.md"
    assert skill.is_file(), "Claude Code only discovers project skills under .claude/skills"

    content = skill.read_text(encoding="utf-8")
    frontmatter = content.split("---", 2)[1]
    assert "name: skytrack" in frontmatter
    assert "$ARGUMENTS" in content


def test_specialized_playbooks_are_not_public_slash_variants() -> None:
    skill_root = PROJECT_ROOT / ".claude" / "skills"
    assert skill_root.is_dir(), "Public skill directory is missing"
    assert {entry.name for entry in skill_root.iterdir() if entry.is_dir()} == {"skytrack"}
