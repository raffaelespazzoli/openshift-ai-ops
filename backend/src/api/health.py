"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config.logging import Component, get_logger
from ..db import get_pool

router = APIRouter()
logger = get_logger(Component.API)


@router.get("/healthz")
async def healthz() -> JSONResponse:
    """Check service health including database connectivity."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        logger.info("Health check passed", extra={"component": "api"})
        return JSONResponse(
            status_code=200,
            content={"status": "healthy", "database": "connected"},
        )
    except Exception:
        logger.warning("Health check failed — database unreachable", extra={"component": "api"})
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"},
        )
