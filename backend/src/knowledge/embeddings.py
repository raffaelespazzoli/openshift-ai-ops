"""Text embedding via OpenAI-compatible endpoint (AD-13).

Generates vector embeddings using the configured embedding model.
Compatible with vLLM, ollama, Azure OpenAI, etc.
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from ..config.knowledge_settings import get_knowledge_settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Uses the OpenAI embeddings API format via the configured endpoint.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (one per input text).
    """
    if not texts:
        return []

    settings = get_knowledge_settings()
    client = AsyncOpenAI(
        base_url=settings.embedding_endpoint,
        api_key=os.environ.get(settings.embedding_api_key_env, "not-set"),
    )
    response = await client.embeddings.create(
        input=texts,
        model=settings.embedding_model,
    )
    return [item.embedding for item in response.data]
