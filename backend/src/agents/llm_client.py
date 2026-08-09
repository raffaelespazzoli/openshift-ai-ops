"""LLM client factory — per-agent-role ChatOpenAI instances (AD-7).

Uses ChatOpenAI with base_url for multi-provider support (vLLM, ollama,
Azure OpenAI, etc.). All providers expose an OpenAI-compatible API.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from ..config.llm_settings import AgentRole, get_agent_llm_config


def get_chat_model(role: AgentRole) -> ChatOpenAI:
    """Create a ChatOpenAI instance configured for the given agent role.

    Args:
        role: The agent role to configure (orchestrator, skeptic, planner).

    Returns:
        A ChatOpenAI instance pointing to the role's configured endpoint.
    """
    config = get_agent_llm_config(role)
    return ChatOpenAI(
        base_url=config.endpoint_url,
        model=config.model_name,
        temperature=config.temperature,
        api_key=os.environ.get(config.api_key_env, "not-set"),
        max_tokens=config.max_tokens,
    )
