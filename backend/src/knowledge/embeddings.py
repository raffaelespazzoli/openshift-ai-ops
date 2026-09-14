"""Text embedding via configurable provider (AD-13).

Supports multiple embedding backends through ``EMBEDDING_PROVIDER``:

* ``openai`` (default) – OpenAI-compatible ``/v1/embeddings``
  (works with OpenAI, vLLM, Ollama /v1, MaaS, OpenRouter).
* ``ollama`` – Native Ollama embeddings API (no /v1 compat needed).

Anthropic does not offer an embeddings API; use ``openai`` or ``ollama``
for embeddings when using Anthropic for chat.
"""

from __future__ import annotations

import os

from ..config.knowledge_settings import get_knowledge_settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Dispatches to the configured embedding provider.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (one per input text).
    """
    if not texts:
        return []

    settings = get_knowledge_settings()
    provider = settings.embedding_provider.strip().lower()

    if provider == "ollama":
        return await _embed_ollama(texts, settings)
    return await _embed_openai(texts, settings)


async def _embed_openai(texts: list[str], settings) -> list[list[float]]:
    """Embed via OpenAI-compatible /v1/embeddings endpoint."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=settings.embedding_endpoint,
        api_key=os.environ.get(settings.embedding_api_key_env, "not-set"),
        timeout=60.0,
    )
    response = await client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
    )
    return [item.embedding for item in response.data]


async def _embed_ollama(texts: list[str], settings) -> list[list[float]]:
    """Embed via native Ollama API."""
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required for EMBEDDING_PROVIDER=ollama. "
            "Install it with: pip install 'openshift-ai-ops[ollama]'"
        ) from exc

    embedder = OllamaEmbeddings(
        base_url=settings.embedding_endpoint,
        model=settings.embedding_model,
    )
    return await embedder.aembed_documents(texts)
