"""API integration tests — health endpoint."""

import pytest


@pytest.mark.api
async def test_health_endpoint_returns_200(async_client):
    """Health endpoint returns 200 when database is connected."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.api
async def test_health_response_has_request_id_header(async_client):
    """Health endpoint includes X-Request-ID header."""
    response = await async_client.get("/healthz")
    assert "x-request-id" in response.headers
