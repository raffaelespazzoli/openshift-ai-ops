"""Unit tests for agentic skill registry (AC: #4, #5).

Tests skill loading, classification, and write-access blocking.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.config.skills_settings import SkillsSettings
from src.knowledge.skills import SkillDefinition, SkillRegistry, skill_to_tool
from src.models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource


def _create_skill_dir(
    base: Path,
    name: str,
    access_level: str,
    description: str = "",
    default_tool: str = "describe_resource",
) -> Path:
    """Helper to create a skill directory with SKILL.md."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    tool_line = f'default_tool: "{default_tool}"\n' if default_tool else ""
    content = f"""# {name}

{description or f'Skill for {name}'}

---
access_level: "{access_level}"
{tool_line}---
"""
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


class TestSkillRegistry:
    """Tests for SkillRegistry loading and classification."""

    @pytest.mark.unit
    def test_loads_skills_from_directory(self, tmp_path):
        """Registry loads skills from directories containing SKILL.md."""
        _create_skill_dir(tmp_path, "cluster-troubleshoot", "read-only", "Diagnose cluster issues")
        _create_skill_dir(tmp_path, "rbac-security", "read-only", "RBAC analysis")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        all_skills = registry.get_all_skills()
        assert len(all_skills) == 2

    @pytest.mark.unit
    def test_read_only_skills_included_in_diagnosis(self, tmp_path):
        """get_diagnosis_skills returns only read-only skills."""
        _create_skill_dir(tmp_path, "cluster-troubleshoot", "read-only")
        _create_skill_dir(tmp_path, "cluster-ops", "read-write")
        _create_skill_dir(tmp_path, "rbac-security", "read-only")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        diagnosis_skills = registry.get_diagnosis_skills()
        names = [s.name for s in diagnosis_skills]
        assert "cluster-troubleshoot" in names
        assert "rbac-security" in names
        assert "cluster-ops" not in names

    @pytest.mark.unit
    def test_read_write_skills_excluded_from_diagnosis(self, tmp_path):
        """get_diagnosis_skills excludes read-write skills (AC #5)."""
        _create_skill_dir(tmp_path, "cluster-ops", "read-write")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        diagnosis_skills = registry.get_diagnosis_skills()
        assert len(diagnosis_skills) == 0

    @pytest.mark.unit
    def test_missing_directory_handled_gracefully(self):
        """Missing skills directory doesn't crash — returns empty registry."""
        settings = SkillsSettings(skills_directory="/nonexistent/path/skills")
        registry = SkillRegistry(settings=settings)

        assert registry.get_diagnosis_skills() == []
        assert registry.get_all_skills() == []

    @pytest.mark.unit
    def test_empty_directory_handled_gracefully(self, tmp_path):
        """Empty skills directory returns empty lists."""
        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        assert registry.get_diagnosis_skills() == []

    @pytest.mark.unit
    def test_directory_without_skill_md_skipped(self, tmp_path):
        """Directories without SKILL.md are skipped."""
        (tmp_path / "not-a-skill").mkdir()
        (tmp_path / "not-a-skill" / "README.md").write_text("Not a skill")
        _create_skill_dir(tmp_path, "real-skill", "read-only")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        all_skills = registry.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].name == "real-skill"

    @pytest.mark.unit
    def test_skill_definition_fields_populated(self, tmp_path):
        """Skill definitions have correct name, description, access_level."""
        _create_skill_dir(tmp_path, "cluster-troubleshoot", "read-only", "Diagnose cluster issues")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        skills = registry.get_all_skills()
        assert len(skills) == 1
        skill = skills[0]
        assert skill.name == "cluster-troubleshoot"
        assert skill.access_level == "read-only"
        assert "Diagnose cluster issues" in skill.description

    @pytest.mark.unit
    def test_enabled_skills_filter(self, tmp_path):
        """Only enabled skills are returned by get_diagnosis_skills."""
        _create_skill_dir(tmp_path, "enabled-skill", "read-only")
        _create_skill_dir(tmp_path, "disabled-skill", "read-only")

        settings = SkillsSettings(
            skills_directory=str(tmp_path),
            enabled_skills=("enabled-skill",),
        )
        registry = SkillRegistry(settings=settings)

        diagnosis_skills = registry.get_diagnosis_skills()
        names = [s.name for s in diagnosis_skills]
        assert "enabled-skill" in names
        assert "disabled-skill" not in names

    @pytest.mark.unit
    def test_missing_access_level_defaults_to_blocked(self, tmp_path):
        """Skills without access_level metadata are classified as read-write (blocked)."""
        skill_dir = tmp_path / "unknown-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# unknown-skill\n\nA skill without access metadata.\n")

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        all_skills = registry.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].access_level == "read-write"
        assert registry.get_diagnosis_skills() == []

    @pytest.mark.unit
    def test_malformed_access_level_defaults_to_blocked(self, tmp_path):
        """Skills with malformed access_level metadata are classified as read-write (blocked)."""
        skill_dir = tmp_path / "bad-metadata"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# bad-metadata\n\nA skill.\n\n---\naccess_level: \"readwrite\"\n---\n"
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        all_skills = registry.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].access_level == "read-write"
        assert registry.get_diagnosis_skills() == []


    @pytest.mark.unit
    def test_read_only_skill_without_default_tool_rejected(self, tmp_path):
        """Read-only skills without default_tool metadata are rejected at load time."""
        skill_dir = tmp_path / "no-tool-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# no-tool-skill\n\nA read-only skill without default_tool.\n\n---\n"
            'access_level: "read-only"\n---\n'
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        assert registry.get_all_skills() == []
        assert registry.get_diagnosis_skills() == []

    @pytest.mark.unit
    def test_read_write_skill_without_default_tool_still_loaded(self, tmp_path):
        """Read-write skills without default_tool are still loaded (blocked at diagnosis)."""
        skill_dir = tmp_path / "rw-no-tool"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# rw-no-tool\n\nA write skill.\n\n---\n"
            'access_level: "read-write"\n---\n'
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        all_skills = registry.get_all_skills()
        assert len(all_skills) == 1
        assert all_skills[0].access_level == "read-write"
        assert registry.get_diagnosis_skills() == []

    @pytest.mark.unit
    def test_quoted_default_tool_parsed_correctly(self, tmp_path):
        """Quoted default_tool values are parsed without trailing quote chars."""
        skill_dir = tmp_path / "quoted-tool-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '# quoted-tool-skill\n\nA skill with quoted default_tool.\n\n---\n'
            'access_level: "read-only"\n'
            'default_tool: "describe_resource"\n---\n'
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        skills = registry.get_all_skills()
        assert len(skills) == 1
        assert skills[0].default_tool == "describe_resource"

    @pytest.mark.unit
    def test_single_quoted_default_tool_parsed_correctly(self, tmp_path):
        """Single-quoted default_tool values are parsed without trailing quote chars."""
        skill_dir = tmp_path / "sq-tool-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# sq-tool-skill\n\nA skill.\n\n---\n"
            "access_level: 'read-only'\n"
            "default_tool: 'get_resources'\n---\n"
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        skills = registry.get_all_skills()
        assert len(skills) == 1
        assert skills[0].default_tool == "get_resources"

    @pytest.mark.unit
    def test_unquoted_default_tool_parsed_correctly(self, tmp_path):
        """Unquoted default_tool values are parsed correctly."""
        skill_dir = tmp_path / "unquoted-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# unquoted-skill\n\nA skill.\n\n---\n"
            "access_level: read-only\n"
            "default_tool: get_events\n---\n"
        )

        settings = SkillsSettings(skills_directory=str(tmp_path))
        registry = SkillRegistry(settings=settings)

        skills = registry.get_all_skills()
        assert len(skills) == 1
        assert skills[0].default_tool == "get_events"


class TestSkillToTool:
    """Tests for skill_to_tool — bound skill execution."""

    @pytest.mark.unit
    async def test_tool_is_bound_to_skill_default_tool(self, tmp_path):
        """Generated tool uses the skill's default_tool, not an arbitrary one."""
        from datetime import datetime, timezone

        skill = SkillDefinition(
            name="cluster-troubleshoot",
            description="Diagnose cluster issues",
            access_level="read-only",
            skill_path=tmp_path / "cluster-troubleshoot",
            default_tool="describe_resource",
        )

        mock_artifact = EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="describe_resource({})",
            result="resource details here",
            timestamp=datetime.now(timezone.utc),
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_artifact)

        tool_fn = skill_to_tool(skill, mock_client)
        result = await tool_fn.ainvoke({"query": "check node status"})

        assert result["type"] == "evidence"
        assert result["source"] == EvidenceSource.AGENTIC_SKILL.value
        assert "cluster-troubleshoot" in result["query"]
        mock_client.query.assert_called_once()
        call_args = mock_client.query.call_args
        assert call_args[0][0] == "describe_resource"

    @pytest.mark.unit
    async def test_tool_forwards_query_context_to_mcp(self, tmp_path):
        """Generated tool forwards the query text through to the MCP tool arguments."""
        from datetime import datetime, timezone

        skill = SkillDefinition(
            name="node-diag",
            description="Node diagnostics",
            access_level="read-only",
            skill_path=tmp_path / "node-diag",
            default_tool="describe_resource",
        )

        mock_artifact = EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="describe_resource({})",
            result="node details",
            timestamp=datetime.now(timezone.utc),
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_artifact)

        tool_fn = skill_to_tool(skill, mock_client)
        await tool_fn.ainvoke({
            "query": "why is this node not ready",
            "namespace": "kube-system",
            "resource_type": "Node",
            "name": "worker-1",
        })

        call_args = mock_client.query.call_args
        mcp_arguments = call_args[0][1]
        assert mcp_arguments["query"] == "why is this node not ready"
        assert mcp_arguments["namespace"] == "kube-system"
        assert mcp_arguments["kind"] == "Node"
        assert mcp_arguments["name"] == "worker-1"

    @pytest.mark.unit
    async def test_tool_passes_different_queries_differently(self, tmp_path):
        """Different diagnostic queries result in different MCP call arguments."""
        from datetime import datetime, timezone

        skill = SkillDefinition(
            name="diag-skill",
            description="Diagnostics",
            access_level="read-only",
            skill_path=tmp_path / "diag-skill",
            default_tool="describe_resource",
        )

        mock_artifact = EvidenceArtifact(
            source=EvidenceSource.MCP_CLUSTER,
            query="describe_resource({})",
            result="details",
            timestamp=datetime.now(timezone.utc),
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_artifact)

        tool_fn = skill_to_tool(skill, mock_client)

        await tool_fn.ainvoke({"query": "check memory pressure"})
        first_args = mock_client.query.call_args[0][1]

        await tool_fn.ainvoke({"query": "check disk pressure"})
        second_args = mock_client.query.call_args[0][1]

        assert first_args["query"] == "check memory pressure"
        assert second_args["query"] == "check disk pressure"
        assert first_args["query"] != second_args["query"]

    @pytest.mark.unit
    async def test_tool_delegates_timeout_to_mcp_client(self, tmp_path):
        """Skill tool lets the MCP client handle timeouts and preserves timeout_seconds metadata."""
        skill = SkillDefinition(
            name="timeout-skill",
            description="Test timeout delegation",
            access_level="read-only",
            skill_path=tmp_path / "timeout-skill",
            default_tool="describe_resource",
        )

        mock_gap = EvidenceGap(
            query="describe_resource({})",
            reason="MCP query timed out",
            timeout_seconds=45.0,
        )
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_gap)

        tool_fn = skill_to_tool(skill, mock_client)
        result = await tool_fn.ainvoke({"query": "check node"})

        assert result["type"] == "evidence_gap"
        assert result["reason"] == "MCP query timed out"
        assert result["timeout_seconds"] == 45.0

    @pytest.mark.unit
    async def test_tool_does_not_accept_arbitrary_tool_name(self, tmp_path):
        """Generated tool signature does not have a tool_name parameter."""
        skill = SkillDefinition(
            name="test-skill",
            description="Test skill",
            access_level="read-only",
            skill_path=tmp_path / "test-skill",
            default_tool="get_resources",
        )

        mock_client = AsyncMock()
        tool_fn = skill_to_tool(skill, mock_client)
        schema = tool_fn.args_schema.model_json_schema() if tool_fn.args_schema else {}
        properties = schema.get("properties", {})
        assert "tool_name" not in properties
        assert "query" in properties
