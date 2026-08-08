"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config.logging import Component, get_logger, request_id_var, setup_logging
from ..config.settings import get_correlation_settings
from ..db import close_pool, get_pool
from ..pipeline.correlator import seal_expired_groups
from .health import router as health_router
from .webhooks import router as webhooks_router

setup_logging()
logger = get_logger(Component.API)


async def _background_sealing_sweep() -> None:
    """Periodic background task that seals expired correlation groups.

    Ensures groups are sealed at max age even when no new alerts arrive.
    Runs every sealing_check_interval_seconds (default 10s).
    """
    settings = get_correlation_settings()
    interval = settings.sealing_check_interval_seconds
    while True:
        try:
            await asyncio.sleep(interval)
            pool = await get_pool()
            async with pool.acquire() as conn:
                sealed = await seal_expired_groups(conn)
                if sealed:
                    logger.info(
                        "Background sweep sealed groups",
                        extra={"sealed_count": sealed},
                    )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in background sealing sweep")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("Application starting", extra={"component": "api"})
    sealing_task = asyncio.create_task(_background_sealing_sweep())
    yield
    sealing_task.cancel()
    try:
        await sealing_task
    except asyncio.CancelledError:
        pass
    await close_pool()
    logger.info("Application shutting down", extra={"component": "api"})


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="OpenShift AI Ops",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = str(uuid.uuid4())
        request_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    app.include_router(health_router)
    app.include_router(webhooks_router)

    return app


app = create_app()
