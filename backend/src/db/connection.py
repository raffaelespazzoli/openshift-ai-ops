"""Database connection management via asyncpg."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

import asyncpg

_pool: asyncpg.Pool | None = None


def _get_db_params() -> dict[str, str]:
    """Return raw database connection parameters from environment."""
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "user": os.environ.get("POSTGRES_USER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "database": os.environ.get("POSTGRES_DB", "openshift_ai_ops"),
    }


def get_db_url() -> str:
    """Build the PostgreSQL DSN from environment variables.

    User and password are percent-encoded so special characters
    (e.g. ``@``, ``:``, ``/``) sourced from Kubernetes secrets are safe.
    """
    p = _get_db_params()
    user = quote_plus(p["user"])
    password = quote_plus(p["password"])
    return f"postgresql://{user}:{password}@{p['host']}:{p['port']}/{p['database']}"


def _get_pool_init_hook():
    """Return pgvector's register_vector as pool init callback, or None."""
    try:
        from pgvector.asyncpg import register_vector
        return register_vector
    except ImportError:
        return None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool.

    Passes credentials as keyword arguments to avoid DSN-encoding edge cases.
    When pgvector is installed, every pooled connection automatically has
    vector types registered via the pool's ``init`` callback.
    """
    global _pool
    if _pool is None:
        p = _get_db_params()
        _pool = await asyncpg.create_pool(
            host=p["host"],
            port=int(p["port"]),
            user=p["user"],
            password=p["password"],
            database=p["database"],
            min_size=2,
            max_size=10,
            init=_get_pool_init_hook(),
        )
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
