"""Unit tests for API envelope and error models."""

import uuid
from datetime import datetime, timezone

import pytest

from src.models.api import (
    ERROR_INTERNAL,
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    ERROR_VALIDATION,
    ApiError,
    ApiMeta,
    ApiResponse,
)


pytestmark = pytest.mark.unit


class TestApiMeta:
    def test_default_fields_populated(self):
        meta = ApiMeta()
        assert meta.timestamp is not None
        assert meta.request_id != ""
        uuid.UUID(meta.request_id)  # validates UUID format

    def test_pagination_fields_optional(self):
        meta = ApiMeta()
        assert meta.page is None
        assert meta.page_size is None
        assert meta.total is None

    def test_pagination_fields_settable(self):
        meta = ApiMeta(page=2, page_size=50, total=142)
        assert meta.page == 2
        assert meta.page_size == 50
        assert meta.total == 142

    def test_timestamp_is_utc(self):
        meta = ApiMeta()
        assert meta.timestamp.tzinfo is not None


class TestApiResponse:
    def test_envelope_structure(self):
        resp = ApiResponse(data={"key": "value"})
        dumped = resp.model_dump(mode="json")
        assert "data" in dumped
        assert "meta" in dumped
        assert dumped["data"] == {"key": "value"}
        assert "timestamp" in dumped["meta"]
        assert "request_id" in dumped["meta"]

    def test_generic_data_type(self):
        resp = ApiResponse(data=[1, 2, 3])
        assert resp.data == [1, 2, 3]

    def test_paginated_envelope(self):
        meta = ApiMeta(page=1, page_size=50, total=100)
        resp = ApiResponse(data=[], meta=meta)
        dumped = resp.model_dump(mode="json")
        assert dumped["meta"]["page"] == 1
        assert dumped["meta"]["page_size"] == 50
        assert dumped["meta"]["total"] == 100


class TestApiError:
    def test_error_structure(self):
        error = ApiError(
            error="Not found",
            code=ERROR_NOT_FOUND,
            detail={"id": "abc-123"},
        )
        dumped = error.model_dump(mode="json")
        assert dumped["error"] == "Not found"
        assert dumped["code"] == "NOT_FOUND"
        assert dumped["detail"] == {"id": "abc-123"}

    def test_detail_defaults_to_empty_dict(self):
        error = ApiError(error="Internal error", code=ERROR_INTERNAL)
        dumped = error.model_dump(mode="json")
        assert dumped["detail"] == {}

    def test_error_codes_defined(self):
        assert ERROR_UNAUTHORIZED == "UNAUTHORIZED"
        assert ERROR_NOT_FOUND == "NOT_FOUND"
        assert ERROR_VALIDATION == "VALIDATION_ERROR"
        assert ERROR_INTERNAL == "INTERNAL_ERROR"
