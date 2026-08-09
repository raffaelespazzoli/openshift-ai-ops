"""Per-agent LLM configuration layer (AD-7).

Provides AgentLLMConfig, AgentRole, and factory functions for resolving
per-role LLM configuration from environment variables. Helm values seed
the env vars; runtime API override is Story 6.1 scope.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SKEPTIC = "skeptic"
    PLANNER = "planner"


@dataclass(frozen=True)
class AgentLLMConfig:
    """LLM configuration for a specific agent role."""

    endpoint_url: str
    model_name: str
    temperature: float = 0.0
    api_key_env: str = "LLM_API_KEY"
    thinking_mode: bool = False
    max_tokens: int = 4096

    @classmethod
    def from_env(cls, role: AgentRole) -> AgentLLMConfig:
        """Resolve config for a specific role from environment variables.

        Layered override: role-specific env var > shared env var > default.
        E.g. LLM_ORCHESTRATOR_ENDPOINT > LLM_ENDPOINT > default.
        """
        prefix = f"LLM_{role.value.upper()}"
        return cls(
            endpoint_url=os.environ.get(
                f"{prefix}_ENDPOINT",
                os.environ.get("LLM_ENDPOINT", "http://localhost:11434/v1"),
            ),
            model_name=os.environ.get(
                f"{prefix}_MODEL",
                os.environ.get("LLM_MODEL", "gpt-4o"),
            ),
            temperature=float(
                os.environ.get(
                    f"{prefix}_TEMPERATURE",
                    os.environ.get("LLM_TEMPERATURE", "0.0"),
                )
            ),
            api_key_env=os.environ.get(
                f"{prefix}_API_KEY_ENV", "LLM_API_KEY"
            ),
            thinking_mode=os.environ.get(
                f"{prefix}_THINKING_MODE", "false"
            ).lower() == "true",
            max_tokens=int(
                os.environ.get(
                    f"{prefix}_MAX_TOKENS",
                    os.environ.get("LLM_MAX_TOKENS", "4096"),
                )
            ),
        )


_configs: dict[AgentRole, AgentLLMConfig] = {}


def get_agent_llm_config(role: AgentRole) -> AgentLLMConfig:
    """Get or create the cached LLM config for a given agent role."""
    if role not in _configs:
        _configs[role] = AgentLLMConfig.from_env(role)
    return _configs[role]


def reset_llm_settings() -> None:
    """Reset cached settings (for testing)."""
    _configs.clear()
