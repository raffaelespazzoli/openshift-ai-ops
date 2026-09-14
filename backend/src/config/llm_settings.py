"""Per-agent LLM configuration layer (AD-7).

Provides AgentLLMConfig, AgentRole, LLMProvider, and factory functions for
resolving per-role LLM configuration from environment variables. Helm values
seed the env vars; runtime API override is Story 6.1 scope.

Supported providers (``LLM_PROVIDER`` / ``LLM_{ROLE}_PROVIDER``):

* ``openai``    – Any OpenAI-compatible endpoint (OpenAI, vLLM, MaaS, Ollama /v1).
* ``anthropic`` – Native Anthropic Messages API (requires ``langchain-anthropic``).
* ``ollama``    – Native Ollama API without the ``/v1`` compat layer
                  (requires ``langchain-ollama``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

# OpenAI Chat Completions + Ollama OpenAI-compat `/v1/chat/completions`.
# Ollama auto-enables thinking for capable models when this field is omitted,
# which can exhaust max_tokens on the reasoning trace and return empty content.
REASONING_EFFORT_VALUES = frozenset({"none", "minimal", "low", "medium", "high"})


class LLMProvider(StrEnum):
    """Supported LLM provider backends."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


_VALID_PROVIDERS = frozenset(p.value for p in LLMProvider)


class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SKEPTIC = "skeptic"
    PLANNER = "planner"
    REMEDIATION_SKEPTIC = "remediation_skeptic"


def _env_for_role(role: AgentRole, suffix: str, default: str | None = None) -> str | None:
    """Role-specific env var, then shared LLM_{suffix}, then default."""
    prefix = f"LLM_{role.value.upper()}"
    value = os.environ.get(f"{prefix}_{suffix}")
    if value is not None:
        return value
    value = os.environ.get(f"LLM_{suffix}")
    if value is not None:
        return value
    return default


def parse_reasoning_effort(role: AgentRole) -> str | None:
    """Resolve reasoning effort for a role.

    ``LLM_{ROLE}_REASONING_EFFORT`` / ``LLM_REASONING_EFFORT`` accept
    none | minimal | low | medium | high. Empty/unset omits the request
    field (provider default). Legacy ``LLM_*_THINKING_MODE=true`` maps to
    ``medium`` when no effort is set.
    """
    raw = (_env_for_role(role, "REASONING_EFFORT", "") or "").strip().lower()
    if raw:
        if raw not in REASONING_EFFORT_VALUES:
            allowed = ", ".join(sorted(REASONING_EFFORT_VALUES))
            raise ValueError(
                f"Invalid LLM reasoning effort {raw!r}; expected one of: {allowed}"
            )
        return raw
    thinking = (_env_for_role(role, "THINKING_MODE", "false") or "false").lower() == "true"
    return "medium" if thinking else None


def _parse_provider(role: AgentRole) -> LLMProvider:
    """Resolve the LLM provider for a role.

    ``LLM_{ROLE}_PROVIDER`` / ``LLM_PROVIDER`` accept openai | anthropic | ollama.
    Default is ``openai`` for backward compatibility.
    """
    raw = (_env_for_role(role, "PROVIDER", "openai") or "openai").strip().lower()
    if raw not in _VALID_PROVIDERS:
        allowed = ", ".join(sorted(_VALID_PROVIDERS))
        raise ValueError(
            f"Invalid LLM provider {raw!r}; expected one of: {allowed}"
        )
    return LLMProvider(raw)


@dataclass(frozen=True)
class AgentLLMConfig:
    """LLM configuration for a specific agent role."""

    provider: LLMProvider = LLMProvider.OPENAI
    endpoint_url: str = ""
    model_name: str = ""
    temperature: float = 0.0
    api_key_env: str = "LLM_API_KEY"
    thinking_mode: bool = False
    reasoning_effort: str | None = None
    max_tokens: int = 4096

    @classmethod
    def from_env(cls, role: AgentRole) -> AgentLLMConfig:
        """Resolve config for a specific role from environment variables.

        Layered override: role-specific env var > shared env var > default.
        E.g. LLM_ORCHESTRATOR_ENDPOINT > LLM_ENDPOINT > default.
        """
        provider = _parse_provider(role)
        reasoning_effort = parse_reasoning_effort(role)

        default_endpoint = {
            LLMProvider.OPENAI: "http://localhost:11434/v1",
            LLMProvider.ANTHROPIC: "https://api.anthropic.com",
            LLMProvider.OLLAMA: "http://localhost:11434",
        }[provider]

        default_model = {
            LLMProvider.OPENAI: "gpt-4o",
            LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
            LLMProvider.OLLAMA: "qwen3:8b",
        }[provider]

        default_api_key_env = {
            LLMProvider.OPENAI: "LLM_API_KEY",
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            LLMProvider.OLLAMA: "LLM_API_KEY",
        }[provider]

        return cls(
            provider=provider,
            endpoint_url=_env_for_role(role, "ENDPOINT", default_endpoint)
            or default_endpoint,
            model_name=_env_for_role(role, "MODEL", default_model) or default_model,
            temperature=float(_env_for_role(role, "TEMPERATURE", "0.0") or "0.0"),
            api_key_env=_env_for_role(role, "API_KEY_ENV", default_api_key_env)
            or default_api_key_env,
            reasoning_effort=reasoning_effort,
            thinking_mode=reasoning_effort not in (None, "none"),
            max_tokens=int(_env_for_role(role, "MAX_TOKENS", "4096") or "4096"),
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


