"""Unit tests for statistics API endpoints (Story 5.5)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from src.api.auth import (
    AuthenticationError,
    UserInfo,
    get_current_user,
    handle_authentication_error,
)
from src.api.statistics import TimeRange, _compute_time_bounds, router

pytestmark = pytest.mark.unit


SAMPLE_SUMMARY = {
    "total_incidents": 142,
    "auto_resolved_pct": 67.5,
    "success_failure_ratio": "4.2:1",
    "mttr_seconds": 312,
    "fast_path_hit_rate_pct": 23.8,
    "trends": {
        "total_incidents": "up",
        "auto_resolved_pct": "flat",
        "success_failure_ratio": "up",
        "mttr_seconds": "down",
        "fast_path_hit_rate_pct": "up",
    },
}

SAMPLE_TIMESERIES = {
    "buckets": ["2026-08-14T00:00:00+00:00", "2026-08-14T01:00:00+00:00"],
    "alerts": [5, 3],
    "diagnoses": [4, 3],
    "resolutions": [3, 2],
    "mttr_seconds": [180, 240],
}


def _mock_pool():
    """Create a mock pool whose acquire() returns an async context manager."""
    conn = AsyncMock()
    pool = AsyncMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool, conn


def _create_test_app():
    """Create a minimal FastAPI app with statistics routes and auth bypass."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_exception_handler(AuthenticationError, handle_authentication_error)
    app.include_router(router)
    return app


class TestSummaryEndpoint:
    @patch.dict(os.environ, {"AUTH_DISABLED": "true"})
    @patch("src.api.statistics.get_pool")
    @patch("src.api.statistics.get_summary_stats")
    def test_returns_data_in_envelope(self, mock_stats, mock_get_pool):
        mock_stats.return_value = SAMPLE_SUMMARY
        pool, _ = _mock_pool()
        mock_get_pool.return_value = pool

        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/api/v1/statistics/summary?range=week")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert body["data"]["total_incidents"] == 142
        assert "request_id" in body["meta"]

    @patch.dict(os.environ, {"AUTH_DISABLED": "true"})
    @patch("src.api.statistics.get_pool")
    @patch("src.api.statistics.get_summary_stats")
    def test_defaults_to_week_range(self, mock_stats, mock_get_pool):
        mock_stats.return_value = SAMPLE_SUMMARY
        pool, _ = _mock_pool()
        mock_get_pool.return_value = pool

        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/api/v1/statistics/summary")
        assert resp.status_code == 200

    def test_rejects_invalid_range(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
            app = _create_test_app()
            client = TestClient(app)
            resp = client.get("/api/v1/statistics/summary?range=year")
            assert resp.status_code == 422

    def test_requires_authentication(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": ""}, clear=False):
            app = _create_test_app()
            client = TestClient(app)
            resp = client.get("/api/v1/statistics/summary")
            assert resp.status_code == 401


class TestTimeseriesEndpoint:
    @patch.dict(os.environ, {"AUTH_DISABLED": "true"})
    @patch("src.api.statistics.get_pool")
    @patch("src.api.statistics.get_timeseries_stats")
    def test_returns_data_in_envelope(self, mock_stats, mock_get_pool):
        mock_stats.return_value = SAMPLE_TIMESERIES
        pool, _ = _mock_pool()
        mock_get_pool.return_value = pool

        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/api/v1/statistics/timeseries?range=day")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert body["data"]["buckets"] == SAMPLE_TIMESERIES["buckets"]
        assert body["data"]["alerts"] == SAMPLE_TIMESERIES["alerts"]

    @patch.dict(os.environ, {"AUTH_DISABLED": "true"})
    @patch("src.api.statistics.get_pool")
    @patch("src.api.statistics.get_timeseries_stats")
    def test_accepts_month_range(self, mock_stats, mock_get_pool):
        mock_stats.return_value = SAMPLE_TIMESERIES
        pool, _ = _mock_pool()
        mock_get_pool.return_value = pool

        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/api/v1/statistics/timeseries?range=month")
        assert resp.status_code == 200

    def test_rejects_invalid_range(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": "true"}):
            app = _create_test_app()
            client = TestClient(app)
            resp = client.get("/api/v1/statistics/timeseries?range=year")
            assert resp.status_code == 422

    def test_requires_authentication(self):
        with patch.dict(os.environ, {"AUTH_DISABLED": ""}, clear=False):
            app = _create_test_app()
            client = TestClient(app)
            resp = client.get("/api/v1/statistics/timeseries")
            assert resp.status_code == 401


class TestComputeTimeBounds:
    def test_day_returns_24h_window(self):
        from_t, to_t, prev_from, prev_to = _compute_time_bounds(TimeRange.day)
        assert (to_t - from_t).total_seconds() == pytest.approx(86400, abs=2)
        assert (prev_to - prev_from).total_seconds() == pytest.approx(86400, abs=2)
        assert prev_to == from_t

    def test_week_returns_7d_window(self):
        from_t, to_t, prev_from, prev_to = _compute_time_bounds(TimeRange.week)
        assert (to_t - from_t).total_seconds() == pytest.approx(604800, abs=2)

    def test_month_returns_30d_window(self):
        from_t, to_t, prev_from, prev_to = _compute_time_bounds(TimeRange.month)
        assert (to_t - from_t).total_seconds() == pytest.approx(2592000, abs=2)


class TestSummaryStatsAggregation:
    """Test the db-level aggregation logic with mocked asyncpg."""

    @pytest.mark.asyncio
    async def test_empty_database_returns_zeroed_stats(self):
        from src.db.statistics import get_summary_stats

        now = datetime.now(timezone.utc)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "total": 0,
            "resolved": 0,
            "failed": 0,
            "fast_path_count": 0,
            "mttr_seconds": 0,
        }
        mock_conn.fetchval.return_value = 0

        result = await get_summary_stats(
            mock_conn,
            now,
            now,
            now,
            now,
        )

        assert result["total_incidents"] == 0
        assert result["auto_resolved_pct"] == 0.0
        assert result["success_failure_ratio"] == "0.0:1"
        assert result["mttr_seconds"] == 0
        assert result["fast_path_hit_rate_pct"] == 0.0
        assert all(v == "flat" for v in result["trends"].values())

    @pytest.mark.asyncio
    async def test_trends_computed_correctly(self):
        from src.db.statistics import get_summary_stats

        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()

        current_row = {
            "total": 100,
            "resolved": 80,
            "failed": 20,
            "fast_path_count": 25,
            "mttr_seconds": 300,
        }
        prev_row = {
            "total": 50,
            "resolved": 30,
            "failed": 20,
            "fast_path_count": 5,
            "mttr_seconds": 500,
        }

        mock_conn.fetchrow.side_effect = [current_row, prev_row]
        mock_conn.fetchval.side_effect = [60, 20]

        result = await get_summary_stats(mock_conn, now, now, now, now)

        assert result["total_incidents"] == 100
        assert result["trends"]["total_incidents"] == "up"
        assert result["trends"]["mttr_seconds"] == "down"


class TestTimeseriesDiagnosisBucketing:
    """Regression tests: diagnoses must be bucketed by sealed_at via a
    separate CTE that JOINs immutable_diagnoses, not derived from alerts."""

    @pytest.mark.asyncio
    async def test_sql_uses_immutable_diagnoses_and_sealed_at(self):
        """The query must reference immutable_diagnoses and sealed_at."""
        from src.db.statistics import get_timeseries_stats

        now = datetime.now(timezone.utc)
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        await get_timeseries_stats(mock_conn, now, now, "1 hour")

        mock_conn.fetch.assert_called_once()
        sql = mock_conn.fetch.call_args[0][0]

        assert "immutable_diagnoses" in sql, (
            "Query must JOIN immutable_diagnoses for diagnosis counts"
        )
        assert "sealed_at" in sql, (
            "Query must bucket diagnoses by sealed_at, not created_at"
        )
        assert "diagnosis_counts" in sql, (
            "Query must use a separate diagnosis_counts CTE"
        )

    @pytest.mark.asyncio
    async def test_diagnosis_counts_independent_of_alert_counts(self):
        """When diagnoses are sealed at different times than incident
        creation, the returned diagnosis list must reflect the
        diagnosis_counts CTE — not alert_counts."""
        from src.db.statistics import get_timeseries_stats

        bucket_1 = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)
        bucket_2 = datetime(2026, 8, 14, 1, 0, 0, tzinfo=timezone.utc)
        to_time = datetime(2026, 8, 14, 2, 0, 0, tzinfo=timezone.utc)

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "bucket_start": bucket_1,
                "alerts": 5,
                "diagnoses": 2,
                "resolutions": 3,
                "mttr_seconds": 180,
            },
            {
                "bucket_start": bucket_2,
                "alerts": 3,
                "diagnoses": 7,
                "resolutions": 2,
                "mttr_seconds": 240,
            },
        ]

        result = await get_timeseries_stats(
            mock_conn, bucket_1, to_time, "1 hour"
        )

        assert result["diagnoses"] == [2, 7], (
            "Diagnosis counts must come from the diagnosis_counts CTE "
            "(sealed_at bucketing), not from alert_counts"
        )
        assert result["alerts"] == [5, 3]
        assert result["resolutions"] == [3, 2]
        assert result["mttr_seconds"] == [180, 240]
