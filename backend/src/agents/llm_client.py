"""LLM client factory — per-agent-role chat model instances (AD-7).

Supports multiple providers via a single ``LLM_PROVIDER`` env var:

* ``openai``    – ChatOpenAI  (OpenAI, vLLM, Ollama /v1, MaaS, OpenRouter)
* ``anthropic`` – ChatAnthropic (native Anthropic Messages API)
* ``ollama``    – ChatOllama  (native Ollama API without /v1 compat)

Provider-specific packages (``langchain-anthropic``, ``langchain-ollama``)
are lazy-imported so the base install stays lightweight.
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

from ..config.llm_settings import (
    AgentLLMConfig,
    AgentRole,
    LLMProvider,
    get_agent_llm_config,
)


def get_chat_model(role: AgentRole) -> BaseChatModel:
    """Create a chat model instance configured for the given agent role.

    Dispatches to the appropriate LangChain class based on the resolved
    ``LLM_PROVIDER`` (or ``LLM_{ROLE}_PROVIDER``) env var.

    Args:
        role: The agent role to configure (orchestrator, skeptic, planner, …).

    Returns:
        A BaseChatModel instance pointing to the role's configured endpoint.
    """
    config = get_agent_llm_config(role)
    builders = {
        LLMProvider.OPENAI: _build_openai,
        LLMProvider.ANTHROPIC: _build_anthropic,
        LLMProvider.OLLAMA: _build_ollama,
    }
    return builders[config.provider](config)


# ── Provider builders ──────────────────────────────────────────────────


def _build_openai(config: AgentLLMConfig) -> BaseChatModel:
    """Build a ChatOpenAI instance (OpenAI-compatible endpoints)."""
    from langchain_openai import ChatOpenAI

    kwargs: dict = {
        "base_url": config.endpoint_url,
        "model": config.model_name,
        "temperature": config.temperature,
        "api_key": os.environ.get(config.api_key_env, "not-set"),
        "max_tokens": config.max_tokens,
        "stream_usage": False,
    }
    if config.reasoning_effort is not None:
        kwargs["reasoning_effort"] = config.reasoning_effort
    return ChatOpenAI(**kwargs)


def _build_anthropic(config: AgentLLMConfig) -> BaseChatModel:
    """Build a ChatAnthropic instance (native Anthropic API)."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "langchain-anthropic is required for LLM_PROVIDER=anthropic. "
            "Install it with: pip install 'openshift-ai-ops[anthropic]'"
        ) from exc

    kwargs: dict = {
        "model": config.model_name,
        "api_key": os.environ.get(config.api_key_env, "not-set"),
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }
    # Anthropic uses a different base URL param name.
    default_url = "https://api.anthropic.com"
    if config.endpoint_url and config.endpoint_url != default_url:
        kwargs["anthropic_api_url"] = config.endpoint_url

    if config.reasoning_effort is not None and config.reasoning_effort != "none":
        budget = _anthropic_thinking_budget(config.reasoning_effort, config.max_tokens)
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
        # Anthropic requires temperature=1 when extended thinking is on.
        kwargs["temperature"] = 1.0

    return ChatAnthropic(**kwargs)


def _build_ollama(config: AgentLLMConfig) -> BaseChatModel:
    """Build a ChatOllama instance (native Ollama API)."""
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for LLM_PROVIDER=ollama. "
            "Install it with: pip install 'openshift-ai-ops[ollama]'"
        ) from exc

    kwargs: dict = {
        "base_url": config.endpoint_url,
        "model": config.model_name,
        "temperature": config.temperature,
        "num_predict": config.max_tokens,
    }
    if config.reasoning_effort is not None:
        kwargs["think"] = config.reasoning_effort != "none"
    return ChatOllama(**kwargs)


# ── Helpers ────────────────────────────────────────────────────────────


def _anthropic_thinking_budget(effort: str, max_tokens: int) -> int:
    """Map reasoning_effort labels to Anthropic thinking budget_tokens."""
    ratio = {
        "minimal": 0.1,
        "low": 0.25,
        "medium": 0.5,
        "high": 0.8,
    }.get(effort, 0.5)
    budget = int(max_tokens * ratio)
    return max(budget, 1024)
