"""API response envelope and error models.

Defines the canonical response envelope ({data, meta}) and error
format ({error, code, detail}) used by all REST endpoints (AD-10).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiMeta(BaseModel):
    """Response metadata included in every API envelope."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Canonical API response envelope wrapping data with metadata."""

    data: T
    meta: ApiMeta = Field(default_factory=ApiMeta)


class ApiError(BaseModel):
    """Structured error response format for all API errors."""

    error: str
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)


ERROR_UNAUTHORIZED = "UNAUTHORIZED"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_INTERNAL = "INTERNAL_ERROR"
