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
    learning_store_decay_half_life_days: float = 90.0
    learning_store_similarity_threshold: float = 0.75
    version_relevance_same_major: float = 1.0
    version_relevance_different_major: float = 0.5
    version_relevance_minor_penalty_per_version: float = 0.02
    learning_store_fast_path_threshold: float = 0.90

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
            learning_store_decay_half_life_days=float(
                os.environ.get("LEARNING_STORE_DECAY_HALF_LIFE_DAYS", "90.0")
            ),
            learning_store_similarity_threshold=float(
                os.environ.get("LEARNING_STORE_SIMILARITY_THRESHOLD", "0.75")
            ),
            version_relevance_same_major=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_SAME_MAJOR", "1.0")
            ),
            version_relevance_different_major=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_DIFFERENT_MAJOR", "0.5")
            ),
            version_relevance_minor_penalty_per_version=float(
                os.environ.get("LEARNING_STORE_VERSION_RELEVANCE_MINOR_PENALTY", "0.02")
            ),
            learning_store_fast_path_threshold=float(
                os.environ.get("LEARNING_STORE_FAST_PATH_THRESHOLD", "0.90")
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


def apply_overrides(overrides: dict[str, str]) -> None:
    """Apply runtime DB overrides to the cached settings (AD-7 layered override).

    Rebuilds the singleton with override values applied on top
    of the current env-based defaults.
    """
    global _knowledge_settings
    base = _knowledge_settings or KnowledgeSettings.from_env()
    field_map: dict[str, tuple[str, type]] = {
        "decay_half_life_days": ("learning_store_decay_half_life_days", float),
        "similarity_threshold": ("learning_store_similarity_threshold", float),
        "version_relevance_same_major": ("version_relevance_same_major", float),
        "version_relevance_different_major": ("version_relevance_different_major", float),
        "version_relevance_minor_penalty_per_version": (
            "version_relevance_minor_penalty_per_version",
            float,
        ),
        "fast_path_threshold": ("learning_store_fast_path_threshold", float),
    }
    kwargs: dict[str, object] = {}
    for field_name in KnowledgeSettings.__dataclass_fields__:
        kwargs[field_name] = getattr(base, field_name)
    for key, value in overrides.items():
        if key in field_map:
            attr_name, cast = field_map[key]
            kwargs[attr_name] = cast(value)
    _knowledge_settings = KnowledgeSettings(**kwargs)
