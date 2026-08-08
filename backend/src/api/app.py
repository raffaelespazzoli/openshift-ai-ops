"""FastAPI application factory."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config.logging import Component, get_logger, request_id_var, setup_logging
from ..db import close_pool
from .health import router as health_router

setup_logging()
logger = get_logger(Component.API)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("Application starting", extra={"component": "api"})
    yield
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

    return app


app = create_app()
