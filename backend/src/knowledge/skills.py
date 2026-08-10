"""Agentic skill registry — load, classify, and convert skills to tools (AD-2).

Skills are loaded from a mounted container image volume. Only read-only skills
are available during diagnosis (AD-2 RBAC Airlock). Write-access skills are
excluded with logged warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool as langchain_tool

from ..config.logging import Component, get_logger
from ..config.skills_settings import SkillsSettings, get_skills_settings
from ..models.diagnosis import EvidenceArtifact, EvidenceGap, EvidenceSource

logger = get_logger(Component.KNOWLEDGE)


@dataclass
class SkillDefinition:
    """Represents a loaded agentic skill."""

    name: str
    description: str
    access_level: str  # "read-only" or "read-write"
    skill_path: Path
    default_tool: str
    enabled: bool = True


class SkillRegistry:
    """Registry that loads and classifies agentic skills from a directory."""

    def __init__(self, settings: SkillsSettings | None = None) -> None:
        self._settings = settings or get_skills_settings()
        self._skills: dict[str, SkillDefinition] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        """Load skill definitions from the configured directory.

        Supports both flat and nested directory layouts (e.g., the upstream
        openshift/agentic-skills repo uses nested subdirectories).
        """
        skills_dir = Path(self._settings.skills_directory)
        if not skills_dir.exists():
            logger.warning(
                "Skills directory not found — diagnosis proceeds without skills",
                extra={"path": str(skills_dir)},
            )
            return

        for skill_path in self._discover_skill_dirs(skills_dir):
            skill = self._parse_skill(skill_path)
            if skill:
                if self._settings.enabled_skills and skill.name not in self._settings.enabled_skills:
                    skill.enabled = False
                self._skills[skill.name] = skill

        logger.info(
            "Skills loaded",
            extra={"total": len(self._skills), "path": str(skills_dir)},
        )

    def _discover_skill_dirs(self, root: Path) -> list[Path]:
        """Recursively find directories containing a SKILL.md file.

        Handles both flat layouts (skills_dir/skill_name/SKILL.md) and nested
        layouts (skills_dir/category/skill_name/SKILL.md) as used by the
        upstream openshift/agentic-skills repository.
        """
        results: list[Path] = []
        for path in sorted(root.rglob("SKILL.md")):
            results.append(path.parent)
        return results

    def _parse_skill(self, skill_path: Path) -> SkillDefinition | None:
        """Parse a skill definition from its SKILL.md file."""
        skill_md = skill_path / "SKILL.md"
        try:
            content = skill_md.read_text()
        except Exception as exc:
            logger.warning(
                "Failed to read skill file",
                extra={"path": str(skill_md), "error": str(exc)},
            )
            return None

        name = skill_path.name
        description = self._extract_description(content)
        access_level = self._extract_access_level(content)
        default_tool = self._extract_default_tool(content, name)

        if default_tool is None and access_level == "read-only":
            logger.warning(
                "Read-only skill rejected — missing required default_tool metadata",
                extra={"skill": name, "path": str(skill_md)},
            )
            return None

        return SkillDefinition(
            name=name,
            description=description,
            access_level=access_level,
            skill_path=skill_path,
            default_tool=default_tool or "",
        )

    def _extract_description(self, content: str) -> str:
        """Extract description from SKILL.md content.

        Checks YAML frontmatter `description` field first (upstream format),
        then falls back to first non-heading text line.
        """
        match = re.search(r"description:\s*[\"'](.+?)[\"']", content)
        if match:
            return match.group(1)[:200]
        match = re.search(r"description:\s*(.+)", content)
        if match:
            return match.group(1).strip()[:200]
        lines = content.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                return stripped[:200]
        return "Agentic skill"

    def _extract_default_tool(self, content: str, skill_name: str) -> str | None:
        """Extract the default MCP tool name from SKILL.md metadata.

        Supports both the `default_tool` field (project format) and
        `allowed-tools` (upstream openshift/agentic-skills format).
        When `allowed-tools` contains a single entry, uses it as the
        default tool. Returns None when metadata is absent.
        """
        match = re.search(r"default_tool:\s*[\"']?([^\s\"']+)[\"']?", content)
        if match:
            return match.group(1).strip("\"'")
        match = re.search(r"allowed-tools:\s*\[?\s*[\"']?([^\s,\]\"']+)[\"']?", content)
        if match:
            return match.group(1).strip("\"'")
        return None

    def _extract_access_level(self, content: str) -> str:
        """Extract access_level from SKILL.md metadata.

        Supports explicit `access_level` field (project format). When absent,
        infers from `allowed-tools` — if all tools are known read-only MCP
        actions (get_*, list_*, describe_*), classifies as 'read-only'.
        Defaults to 'read-write' (blocked) when metadata is missing or
        ambiguous — fail-closed (AD-2 RBAC Airlock).
        """
        match = re.search(r"access_level:\s*[\"']?(read-only|read-write)[\"']?", content)
        if match:
            return match.group(1)
        match = re.search(r"allowed-tools:\s*\[?([^\]]+)\]?", content)
        if match:
            tools_str = match.group(1).strip()
            tools = [t.strip().strip("\"'") for t in tools_str.split(",")]
            read_only_prefixes = ("get_", "list_", "describe_", "read_", "show_")
            if all(t.startswith(read_only_prefixes) for t in tools if t):
                return "read-only"
        return "read-write"

    def get_diagnosis_skills(self) -> list[SkillDefinition]:
        """Return only read-only, enabled skills for diagnosis stage.

        Write-access skills are excluded with logged warnings.
        """
        read_only: list[SkillDefinition] = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            if skill.access_level == "read-only":
                read_only.append(skill)
            elif skill.access_level == "read-write":
                logger.info(
                    "Skill excluded from diagnosis (write access required)",
                    extra={"skill": skill.name},
                )
        return read_only

    def get_all_skills(self) -> list[SkillDefinition]:
        """Return all loaded skills regardless of access level."""
        return list(self._skills.values())


def skill_to_tool(skill: SkillDefinition, mcp_client: Any):
    """Convert a SkillDefinition into a LangChain @tool function bound to this skill.

    The generated tool is bound to the skill's definition — it uses the
    skill's ``default_tool`` MCP action and accepts a ``query`` parameter
    describing the diagnostic context.  Callers cannot override which MCP
    tool is invoked, ensuring the tool executes skill-specific behaviour
    from SKILL.md rather than acting as a generic MCP passthrough.

    The tool executes via the read-only MCP client (AD-2 RBAC Airlock).
    Each invocation records an EvidenceArtifact with source=AGENTIC_SKILL.

    Args:
        skill: The skill definition to convert.
        mcp_client: ReadOnlyMCPClient instance for cluster queries.

    Returns:
        A LangChain tool function.
    """
    bound_tool_name = skill.default_tool
    bound_skill_name = skill.name

    @langchain_tool(f"skill_{bound_skill_name}", description=skill.description)
    async def execute_skill(
        query: str,
        namespace: str = "default",
        resource_type: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """Execute this agentic skill's diagnostic check via the read-only MCP server.

        Args:
            query: Description of what to check or diagnose.
            namespace: Kubernetes namespace scope for the check.
            resource_type: Optional resource kind to inspect.
            name: Optional specific resource name.
        """
        arguments: dict[str, Any] = {"query": query, "namespace": namespace}
        if resource_type:
            arguments["kind"] = resource_type
        if name:
            arguments["name"] = name

        result = await mcp_client.query(bound_tool_name, arguments)

        if isinstance(result, EvidenceGap):
            return {
                "type": "evidence_gap",
                "source": EvidenceSource.AGENTIC_SKILL.value,
                "query": f"skill_{bound_skill_name}({query})",
                "reason": result.reason,
                "timeout_seconds": result.timeout_seconds,
            }

        return {
            "type": "evidence",
            "source": EvidenceSource.AGENTIC_SKILL.value,
            "query": f"skill_{bound_skill_name}({query})",
            "result": result.result if isinstance(result, EvidenceArtifact) else str(result),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return execute_skill
