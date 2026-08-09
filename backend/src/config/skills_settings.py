"""Agentic skills configuration — directory path, enabled list."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillsSettings:
    """Configuration for agentic skills integration."""

    skills_directory: str = "/skills"
    enabled_skills: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> SkillsSettings:
        enabled_raw = os.environ.get("SKILLS_ENABLED", "")
        enabled = tuple(
            s.strip() for s in enabled_raw.split(",") if s.strip()
        ) if enabled_raw else ()
        return cls(
            skills_directory=os.environ.get("SKILLS_DIRECTORY", "/skills"),
            enabled_skills=enabled,
        )


_skills_settings: SkillsSettings | None = None


def get_skills_settings() -> SkillsSettings:
    """Get or create the singleton skills settings instance."""
    global _skills_settings
    if _skills_settings is None:
        _skills_settings = SkillsSettings.from_env()
    return _skills_settings


def reset_skills_settings() -> None:
    """Reset cached settings (for testing)."""
    global _skills_settings
    _skills_settings = None
