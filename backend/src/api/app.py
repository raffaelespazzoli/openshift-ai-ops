"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config.logging import Component, get_logger, request_id_var, setup_logging
from ..config.settings import get_correlation_settings
from ..db import close_pool, get_pool
from ..db.checkpointer import close_checkpointer, setup_checkpointer
from ..models.api import ERROR_INTERNAL, ERROR_NOT_FOUND, ERROR_VALIDATION, ApiError
from ..pipeline.correlator import seal_expired_groups
from ..pipeline.dispatcher import run_dispatcher, shutdown_pipeline_tasks
from .audit import AuditMiddleware
from .auth import AuthenticationError, handle_authentication_error
from .event_bus import get_event_bus
from .events import router as events_router
from .health import router as health_router
from .incidents import router as incidents_router
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


async def _init_pgvector() -> None:
    """Register pgvector types on the asyncpg pool (AD-13).

    Must be called after pool creation so vector columns can be
    read/written as Python lists.
    """
    try:
        from pgvector.asyncpg import register_vector

        pool = await get_pool()
        async with pool.acquire() as conn:
            await register_vector(conn)
        logger.info("pgvector types registered on asyncpg pool")
    except ImportError:
        logger.warning("pgvector package not installed — vector operations unavailable")
    except Exception:
        logger.warning("pgvector registration failed — vector operations may not work")


async def _ingest_runbooks_on_startup() -> None:
    """Ingest bundled runbooks into pgvector on startup (AD-13).

    Runbooks are bundled at container build time. This runs once on
    startup; refresh = image rebuild. Skips gracefully if the configured
    runbook directory does not exist or is empty.
    """
    try:
        from ..config.knowledge_settings import get_knowledge_settings
        from ..knowledge.ingest import ingest_runbooks

        settings = get_knowledge_settings()
        logger.info(
            "Attempting runbook ingestion",
            extra={"runbooks_directory": settings.runbooks_directory},
        )

        pool = await get_pool()
        async with pool.acquire() as conn:
            from pgvector.asyncpg import register_vector
            await register_vector(conn)
            stats = await ingest_runbooks(conn)

        if stats["files_processed"] == 0:
            logger.info(
                "No runbooks ingested — directory missing or empty (expected if no corpus bundled)",
                extra={"runbooks_directory": settings.runbooks_directory},
            )
        else:
            logger.info("Runbook ingestion complete on startup", extra=stats)
    except ImportError:
        logger.warning("Knowledge modules not available — skipping runbook ingestion")
    except Exception:
        logger.warning("Runbook ingestion failed on startup — RAG search may be limited")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("Application starting", extra={"component": "api"})
    get_event_bus()
    await setup_checkpointer()
    await _init_pgvector()
    await _ingest_runbooks_on_startup()
    sealing_task = asyncio.create_task(_background_sealing_sweep())
    dispatcher_task = asyncio.create_task(run_dispatcher())
    yield
    dispatcher_task.cancel()
    sealing_task.cancel()
    try:
        await dispatcher_task
    except asyncio.CancelledError:
        pass
    try:
        await sealing_task
    except asyncio.CancelledError:
        pass
    await shutdown_pipeline_tasks()
    await close_checkpointer()
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

    app.add_middleware(AuditMiddleware)

    app.add_exception_handler(AuthenticationError, handle_authentication_error)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError):
        """Transform FastAPI request validation errors into structured error format."""
        fields = []
        for err in exc.errors():
            fields.append({
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err.get("msg", "invalid value"),
            })
        error = ApiError(
            error="Validation error",
            code=ERROR_VALIDATION,
            detail={"fields": fields},
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(request: Request, exc: ValidationError):
        """Transform Pydantic validation errors into structured error format."""
        fields = []
        for err in exc.errors():
            fields.append({
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err.get("msg", "invalid value"),
            })
        error = ApiError(
            error="Validation error",
            code=ERROR_VALIDATION,
            detail={"fields": fields},
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Transform HTTP exceptions (404, 405, etc.) into structured error format."""
        status_to_code = {
            404: ERROR_NOT_FOUND,
            405: "METHOD_NOT_ALLOWED",
        }
        code = status_to_code.get(exc.status_code, f"HTTP_{exc.status_code}")
        error = ApiError(
            error=str(exc.detail) if exc.detail else f"HTTP {exc.status_code}",
            code=code,
        )
        return JSONResponse(status_code=exc.status_code, content=error.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all for unhandled exceptions — return structured error."""
        logger.exception(
            "Unhandled exception",
            extra={"path": request.url.path, "method": request.method},
        )
        error = ApiError(
            error="Internal server error",
            code=ERROR_INTERNAL,
        )
        return JSONResponse(status_code=500, content=error.model_dump(mode="json"))

    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(incidents_router)
    app.include_router(events_router)

    return app


app = create_app()
