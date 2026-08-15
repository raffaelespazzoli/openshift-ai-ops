"""Statistics REST endpoints (Story 5.5).

GET /api/v1/statistics/summary — aggregated metrics for summary cards
GET /api/v1/statistics/timeseries — bucketed time-series for charts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Query, Request

from ..config.logging import Component, get_logger, request_id_var
from ..db import get_pool
from ..db.statistics import get_summary_stats, get_timeseries_stats
from ..models.api import ApiMeta, ApiResponse
from .auth import UserInfo, get_current_user

router = APIRouter()
logger = get_logger(Component.API)


class TimeRange(str, Enum):
    day = "day"
    week = "week"
    month = "month"


_RANGE_CONFIG = {
    TimeRange.day: {"delta": timedelta(days=1), "bucket": "1 hour"},
    TimeRange.week: {"delta": timedelta(weeks=1), "bucket": "1 day"},
    TimeRange.month: {"delta": timedelta(days=30), "bucket": "1 day"},
}


def _compute_time_bounds(range_val: TimeRange) -> tuple[datetime, datetime, datetime, datetime]:
    """Compute current and previous period boundaries for a time range."""
    now = datetime.now(timezone.utc)
    delta = _RANGE_CONFIG[range_val]["delta"]
    to_time = now
    from_time = now - delta
    prev_to_time = from_time
    prev_from_time = from_time - delta
    return from_time, to_time, prev_from_time, prev_to_time


@router.get("/api/v1/statistics/summary")
async def get_statistics_summary(
    request: Request,
    user: UserInfo = Depends(get_current_user),
    range: TimeRange = Query(TimeRange.week, alias="range"),
) -> dict:
    """Return aggregated metrics for the statistics summary cards."""
    request.state.user = user

    from_time, to_time, prev_from_time, prev_to_time = _compute_time_bounds(range)

    pool = await get_pool()
    async with pool.acquire() as conn:
        data = await get_summary_stats(conn, from_time, to_time, prev_from_time, prev_to_time)

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(data=data, meta=meta).model_dump(mode="json")


@router.get("/api/v1/statistics/timeseries")
async def get_statistics_timeseries(
    request: Request,
    user: UserInfo = Depends(get_current_user),
    range: TimeRange = Query(TimeRange.week, alias="range"),
) -> dict:
    """Return bucketed time-series data for statistics charts."""
    request.state.user = user

    from_time, to_time, _, _ = _compute_time_bounds(range)
    bucket = _RANGE_CONFIG[range]["bucket"]

    pool = await get_pool()
    async with pool.acquire() as conn:
        data = await get_timeseries_stats(conn, from_time, to_time, bucket)

    meta = ApiMeta(request_id=request_id_var.get() or "")
    return ApiResponse(data=data, meta=meta).model_dump(mode="json")
