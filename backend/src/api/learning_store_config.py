"""Learning Store config API endpoints (Story 4.2, AD-7).

GET  /api/v1/config/learning-store — effective config (Helm + DB overrides)
PUT  /api/v1/config/learning-store — update config keys in DB
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config.knowledge_settings import (
    apply_overrides,
    get_knowledge_settings,
)
from ..config.logging import Component, get_logger
from ..db import get_pool
from ..db.learning_store_config import get_all_config, set_config
from ..models.api import ERROR_VALIDATION, ApiError, ApiMeta, ApiResponse
from .auth import UserInfo, get_current_user

router = APIRouter()
logger = get_logger(Component.API)

VALID_CONFIG_KEYS = frozenset({
    "decay_half_life_days",
    "similarity_threshold",
    "version_relevance_same_major",
    "version_relevance_different_major",
    "version_relevance_minor_penalty_per_version",
})


def _get_effective_config() -> dict[str, float]:
    """Build effective config dict from current KnowledgeSettings singleton."""
    settings = get_knowledge_settings()
    return {
        "decay_half_life_days": settings.learning_store_decay_half_life_days,
        "similarity_threshold": settings.learning_store_similarity_threshold,
        "version_relevance_same_major": settings.version_relevance_same_major,
        "version_relevance_different_major": settings.version_relevance_different_major,
        "version_relevance_minor_penalty_per_version": settings.version_relevance_minor_penalty_per_version,
    }


@router.get("/api/v1/config/learning-store")
async def get_learning_store_config(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> JSONResponse:
    """Return effective Learning Store config (Helm defaults merged with DB overrides)."""
    config = _get_effective_config()
    response = ApiResponse(data=config, meta=ApiMeta())
    return JSONResponse(
        status_code=200, content=response.model_dump(mode="json")
    )


class ConfigUpdateRequest(BaseModel):
    """Request body for PUT config — arbitrary float config keys."""

    model_config = {"extra": "allow"}


@router.put("/api/v1/config/learning-store")
async def update_learning_store_config(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> JSONResponse:
    """Update Learning Store config keys in DB, reload singleton."""
    body = await request.json()

    invalid_keys = set(body.keys()) - VALID_CONFIG_KEYS
    if invalid_keys:
        error = ApiError(
            error="Validation error",
            code=ERROR_VALIDATION,
            detail={"invalid_keys": sorted(invalid_keys), "valid_keys": sorted(VALID_CONFIG_KEYS)},
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    for key, value in body.items():
        try:
            float(value)
        except (TypeError, ValueError):
            error = ApiError(
                error="Validation error",
                code=ERROR_VALIDATION,
                detail={"field": key, "message": f"Value must be numeric, got: {value!r}"},
            )
            return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    pool = await get_pool()
    async with pool.acquire() as conn:
        for key, value in body.items():
            await set_config(conn, key, str(value), user.username)

        all_overrides = await get_all_config(conn)

    apply_overrides(all_overrides)

    config = _get_effective_config()
    response = ApiResponse(data=config, meta=ApiMeta())
    return JSONResponse(
        status_code=200, content=response.model_dump(mode="json")
    )
