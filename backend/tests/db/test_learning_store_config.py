"""DB integration tests for learning_store_config table (Story 4.2, AC #4).

Tests set_config/get_config roundtrip, get_all_config, and update behavior.
Requires testcontainers (pytest -m db).
"""

from __future__ import annotations

import pytest

from src.db.learning_store_config import get_all_config, get_config, set_config


@pytest.mark.db
class TestLearningStoreConfigTable:
    """Tests for the learning_store_config table operations."""

    async def test_table_created_by_migration(self, db_conn):
        """learning_store_config table exists after migration."""
        result = await db_conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'learning_store_config')"
        )
        assert result is True

    async def test_set_config_persists(self, db_conn):
        """set_config persists a key-value pair."""
        await set_config(db_conn, "decay_half_life_days", "45.0", "test-user")
        row = await db_conn.fetchrow(
            "SELECT value, updated_by FROM learning_store_config WHERE key = $1",
            "decay_half_life_days",
        )
        assert row["value"] == "45.0"
        assert row["updated_by"] == "test-user"

    async def test_get_config_returns_value(self, db_conn):
        """get_config returns the stored value."""
        await set_config(db_conn, "decay_half_life_days", "45.0", "test-user")
        result = await get_config(db_conn, "decay_half_life_days")
        assert result == "45.0"

    async def test_get_config_nonexistent_key_returns_none(self, db_conn):
        """get_config for non-existent key returns None."""
        result = await get_config(db_conn, "nonexistent_key")
        assert result is None

    async def test_get_all_config_returns_all_keys(self, db_conn):
        """get_all_config returns all stored config pairs."""
        await set_config(db_conn, "decay_half_life_days", "45.0", "user-a")
        await set_config(db_conn, "similarity_threshold", "0.80", "user-b")
        result = await get_all_config(db_conn)
        assert result["decay_half_life_days"] == "45.0"
        assert result["similarity_threshold"] == "0.80"

    async def test_set_config_updates_existing_key(self, db_conn):
        """set_config on existing key updates value and metadata."""
        await set_config(db_conn, "decay_half_life_days", "45.0", "user-a")
        await set_config(db_conn, "decay_half_life_days", "30.0", "user-b")
        result = await get_config(db_conn, "decay_half_life_days")
        assert result == "30.0"
        row = await db_conn.fetchrow(
            "SELECT updated_by FROM learning_store_config WHERE key = $1",
            "decay_half_life_days",
        )
        assert row["updated_by"] == "user-b"

    async def test_set_config_updates_timestamp(self, db_conn):
        """set_config updates the updated_at timestamp."""
        await set_config(db_conn, "decay_half_life_days", "45.0", "user-a")
        row1 = await db_conn.fetchrow(
            "SELECT updated_at FROM learning_store_config WHERE key = $1",
            "decay_half_life_days",
        )
        await set_config(db_conn, "decay_half_life_days", "30.0", "user-a")
        row2 = await db_conn.fetchrow(
            "SELECT updated_at FROM learning_store_config WHERE key = $1",
            "decay_half_life_days",
        )
        assert row2["updated_at"] >= row1["updated_at"]


@pytest.mark.db
class TestStartupConfigLoading:
    """Tests for startup config loading behavior (AD-7)."""

    async def test_db_override_takes_precedence_over_env(self, db_conn):
        """DB override values should take precedence over env defaults."""
        await set_config(db_conn, "decay_half_life_days", "30.0", "startup-test")
        overrides = await get_all_config(db_conn)
        assert overrides["decay_half_life_days"] == "30.0"

        from src.config.knowledge_settings import (
            KnowledgeSettings,
            apply_overrides,
            get_knowledge_settings,
            reset_knowledge_settings,
        )

        reset_knowledge_settings()
        apply_overrides(overrides)
        settings = get_knowledge_settings()
        assert settings.learning_store_decay_half_life_days == 30.0
        reset_knowledge_settings()
