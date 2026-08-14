"""API tests for Learning Store config endpoints (Story 4.2, AC #4).

Tests GET/PUT /api/v1/config/learning-store with validation,
effective config merging, and audit logging.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.config.knowledge_settings import reset_knowledge_settings

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _auth_disabled():
    with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
        yield


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset KnowledgeSettings singleton between tests."""
    reset_knowledge_settings()
    yield
    reset_knowledge_settings()


async def test_get_returns_effective_config(async_client):
    """GET /api/v1/config/learning-store returns effective config with all keys."""
    response = await async_client.get("/api/v1/config/learning-store")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    data = body["data"]
    assert "decay_half_life_days" in data
    assert "similarity_threshold" in data
    assert "version_relevance_same_major" in data
    assert "version_relevance_different_major" in data
    assert "version_relevance_minor_penalty_per_version" in data
    assert data["decay_half_life_days"] == 90.0
    assert data["version_relevance_same_major"] == 1.0


async def test_put_updates_db_and_returns_merged_config(async_client):
    """PUT updates DB and returns effective config with override applied."""
    response = await async_client.put(
        "/api/v1/config/learning-store",
        json={"decay_half_life_days": 45.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["decay_half_life_days"] == 45.0
    assert body["data"]["version_relevance_same_major"] == 1.0


async def test_put_invalid_key_returns_422(async_client):
    """PUT with invalid key returns 422 validation error."""
    response = await async_client.put(
        "/api/v1/config/learning-store",
        json={"invalid_key": 1.0},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "invalid_keys" in body["detail"]


async def test_put_non_numeric_value_returns_422(async_client):
    """PUT with non-numeric value returns 422 validation error."""
    response = await async_client.put(
        "/api/v1/config/learning-store",
        json={"decay_half_life_days": "not_a_number"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "field" in body["detail"]


async def test_get_after_put_reflects_override(async_client):
    """GET after PUT reflects the previously set override."""
    await async_client.put(
        "/api/v1/config/learning-store",
        json={"version_relevance_different_major": 0.3},
    )
    response = await async_client.get("/api/v1/config/learning-store")
    assert response.status_code == 200
    assert response.json()["data"]["version_relevance_different_major"] == 0.3


async def test_multiple_puts_latest_wins(async_client):
    """Multiple PUTs — latest value wins."""
    await async_client.put(
        "/api/v1/config/learning-store",
        json={"decay_half_life_days": 60.0},
    )
    await async_client.put(
        "/api/v1/config/learning-store",
        json={"decay_half_life_days": 30.0},
    )
    response = await async_client.get("/api/v1/config/learning-store")
    assert response.status_code == 200
    assert response.json()["data"]["decay_half_life_days"] == 30.0


async def test_put_multiple_keys_at_once(async_client):
    """PUT with multiple keys updates all of them."""
    response = await async_client.put(
        "/api/v1/config/learning-store",
        json={
            "decay_half_life_days": 45.0,
            "version_relevance_same_major": 0.95,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["decay_half_life_days"] == 45.0
    assert data["version_relevance_same_major"] == 0.95
