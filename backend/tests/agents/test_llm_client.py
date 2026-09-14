"""Unit tests for the multi-provider LLM client factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.llm_client import get_chat_model
from src.config.llm_settings import (
    AgentRole,
    LLMProvider,
    get_agent_llm_config,
    reset_llm_settings,
)


@pytest.fixture(autouse=True)
def _reset_llm_env(monkeypatch):
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
    monkeypatch.delenv("LLM_ORCHESTRATOR_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("LLM_ORCHESTRATOR_THINKING_MODE", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_ORCHESTRATOR_PROVIDER", raising=False)
    reset_llm_settings()
    yield
    reset_llm_settings()


# ── Provider resolution ────────────────────────────────────────────────


@pytest.mark.unit
def test_default_provider_is_openai():
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.provider == LLMProvider.OPENAI


@pytest.mark.unit
def test_shared_provider_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.provider == LLMProvider.ANTHROPIC


@pytest.mark.unit
def test_role_provider_overrides_shared(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ORCHESTRATOR_PROVIDER", "ollama")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.provider == LLMProvider.OLLAMA


@pytest.mark.unit
def test_invalid_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    with pytest.raises(ValueError, match="deepseek"):
        get_agent_llm_config(AgentRole.ORCHESTRATOR)


# ── Provider-specific defaults ─────────────────────────────────────────


@pytest.mark.unit
def test_anthropic_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.endpoint_url == "https://api.anthropic.com"
    assert "claude" in cfg.model_name
    assert cfg.api_key_env == "ANTHROPIC_API_KEY"


@pytest.mark.unit
def test_ollama_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.endpoint_url == "http://localhost:11434"
    assert cfg.model_name == "qwen3:8b"


# ── OpenAI builder ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_chat_model_openai_basic():
    with patch("langchain_openai.ChatOpenAI") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["stream_usage"] is False


@pytest.mark.unit
def test_get_chat_model_omits_reasoning_effort_by_default():
    with patch("langchain_openai.ChatOpenAI") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    assert "reasoning_effort" not in mock_cls.call_args.kwargs


@pytest.mark.unit
@pytest.mark.parametrize("effort", ["none", "low", "medium", "high", "minimal"])
def test_get_chat_model_passes_reasoning_effort(monkeypatch, effort):
    monkeypatch.setenv("LLM_REASONING_EFFORT", effort)
    with patch("langchain_openai.ChatOpenAI") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    assert mock_cls.call_args.kwargs["reasoning_effort"] == effort


@pytest.mark.unit
def test_role_reasoning_effort_overrides_shared(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    monkeypatch.setenv("LLM_ORCHESTRATOR_REASONING_EFFORT", "high")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.reasoning_effort == "high"
    assert cfg.thinking_mode is True


@pytest.mark.unit
def test_legacy_thinking_mode_maps_to_medium(monkeypatch):
    monkeypatch.setenv("LLM_THINKING_MODE", "true")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.reasoning_effort == "medium"
    assert cfg.thinking_mode is True


@pytest.mark.unit
def test_reasoning_effort_none_disables_thinking_mode(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    cfg = get_agent_llm_config(AgentRole.ORCHESTRATOR)
    assert cfg.reasoning_effort == "none"
    assert cfg.thinking_mode is False


@pytest.mark.unit
def test_invalid_reasoning_effort_raises(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "turbo")
    with pytest.raises(ValueError, match="turbo"):
        get_agent_llm_config(AgentRole.ORCHESTRATOR)


# ── Anthropic builder ──────────────────────────────────────────────────


@pytest.mark.unit
def test_anthropic_builder_basic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-20250514"
    assert kwargs["api_key"] == "sk-ant-test"
    assert "anthropic_api_url" not in kwargs
    assert "thinking" not in kwargs


@pytest.mark.unit
def test_anthropic_builder_custom_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_ENDPOINT", "https://my-proxy.example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    assert mock_cls.call_args.kwargs["anthropic_api_url"] == "https://my-proxy.example.com"


@pytest.mark.unit
def test_anthropic_builder_with_thinking(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")
    monkeypatch.setenv("LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["thinking"]["type"] == "enabled"
    assert kwargs["thinking"]["budget_tokens"] == 4096
    assert kwargs["temperature"] == 1.0


@pytest.mark.unit
def test_anthropic_import_error_gives_helpful_message():
    with (
        patch.dict("os.environ", {"LLM_PROVIDER": "anthropic"}),
        patch.dict("sys.modules", {"langchain_anthropic": None}),
    ):
        reset_llm_settings()
        with pytest.raises(ImportError, match="langchain-anthropic"):
            get_chat_model(AgentRole.ORCHESTRATOR)


# ── Ollama builder ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_ollama_builder_basic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with patch("langchain_ollama.ChatOllama") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["model"] == "qwen3:8b"
    assert kwargs["base_url"] == "http://localhost:11434"
    assert kwargs["num_predict"] == 4096


@pytest.mark.unit
def test_ollama_builder_with_thinking(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "medium")
    with patch("langchain_ollama.ChatOllama") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    assert mock_cls.call_args.kwargs["think"] is True


@pytest.mark.unit
def test_ollama_builder_thinking_disabled_with_none(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    with patch("langchain_ollama.ChatOllama") as mock_cls:
        get_chat_model(AgentRole.ORCHESTRATOR)
    assert mock_cls.call_args.kwargs["think"] is False


@pytest.mark.unit
def test_ollama_import_error_gives_helpful_message():
    with (
        patch.dict("os.environ", {"LLM_PROVIDER": "ollama"}),
        patch.dict("sys.modules", {"langchain_ollama": None}),
    ):
        reset_llm_settings()
        with pytest.raises(ImportError, match="langchain-ollama"):
            get_chat_model(AgentRole.ORCHESTRATOR)
