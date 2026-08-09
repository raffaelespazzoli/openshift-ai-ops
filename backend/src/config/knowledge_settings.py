"""Knowledge retrieval settings — embedding model, RAG thresholds, chunk sizes.

Configuration for the runbook RAG pipeline (AD-13 path 1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_RUNBOOKS_DIR = str(_BACKEND_ROOT / "runbooks")


@dataclass(frozen=True)
class KnowledgeSettings:
    """Configuration for knowledge retrieval and embedding."""

    embedding_endpoint: str = "http://localhost:11434/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key_env: str = "EMBEDDING_API_KEY"
    embedding_dimensions: int = 1536
    chunk_max_tokens: int = 512
    chunk_overlap_tokens: int = 64
    similarity_threshold: float = 0.7
    top_k: int = 5
    runbooks_directory: str = _DEFAULT_RUNBOOKS_DIR

    @classmethod
    def from_env(cls) -> KnowledgeSettings:
        return cls(
            embedding_endpoint=os.environ.get(
                "EMBEDDING_ENDPOINT", "http://localhost:11434/v1"
            ),
            embedding_model=os.environ.get(
                "EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            embedding_api_key_env=os.environ.get(
                "EMBEDDING_API_KEY_ENV", "EMBEDDING_API_KEY"
            ),
            embedding_dimensions=int(
                os.environ.get("EMBEDDING_DIMENSIONS", "1536")
            ),
            chunk_max_tokens=int(os.environ.get("CHUNK_MAX_TOKENS", "512")),
            chunk_overlap_tokens=int(os.environ.get("CHUNK_OVERLAP_TOKENS", "64")),
            similarity_threshold=float(
                os.environ.get("SIMILARITY_THRESHOLD", "0.7")
            ),
            top_k=int(os.environ.get("RAG_TOP_K", "5")),
            runbooks_directory=os.environ.get(
                "RUNBOOKS_DIRECTORY", _DEFAULT_RUNBOOKS_DIR
            ),
        )


_knowledge_settings: KnowledgeSettings | None = None


def get_knowledge_settings() -> KnowledgeSettings:
    """Get or create the singleton knowledge settings instance."""
    global _knowledge_settings
    if _knowledge_settings is None:
        _knowledge_settings = KnowledgeSettings.from_env()
    return _knowledge_settings


def reset_knowledge_settings() -> None:
    """Reset cached settings (for testing)."""
    global _knowledge_settings
    _knowledge_settings = None
