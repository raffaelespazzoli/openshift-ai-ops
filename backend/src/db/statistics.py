"""SQL aggregation queries for statistics dashboard (Story 5.5).

Provides summary metrics (card tiles) and bucketed time-series data
for the statistics charts. Queries run against the incidents and
approval_records tables.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from ..config.logging import Component, get_logger

logger = get_logger(Component.DB)

_TERMINAL_STATES = ("resolved", "failed")


async def get_summary_stats(
    conn: asyncpg.Connection | asyncpg.Pool,
    from_time: datetime,
    to_time: datetime,
    prev_from_time: datetime,
    prev_to_time: datetime,
) -> dict:
    """Aggregate incident counts and metrics for summary cards.

    Computes current-period and previous-period stats, then derives
    trend direction for each metric (up / down / flat within ±5%).
    """
    current = await _aggregate_period(conn, from_time, to_time)
    previous = await _aggregate_period(conn, prev_from_time, prev_to_time)

    def trend(cur: float, prev: float) -> str:
        if prev == 0:
            return "flat" if cur == 0 else "up"
        pct_change = ((cur - prev) / prev) * 100
        if pct_change > 5:
            return "up"
        if pct_change < -5:
            return "down"
        return "flat"

    total = current["total_incidents"]
    prev_total = previous["total_incidents"]

    auto_pct = current["auto_resolved_pct"]
    prev_auto_pct = previous["auto_resolved_pct"]

    successes = current["resolved_count"]
    failures = current["failed_count"]
    if failures > 0:
        ratio = round(successes / failures, 1)
    else:
        ratio = float(successes) if successes > 0 else 0.0
    ratio_str = f"{ratio}:1"

    prev_successes = previous["resolved_count"]
    prev_failures = previous["failed_count"]
    prev_ratio = (prev_successes / prev_failures) if prev_failures > 0 else float(prev_successes)

    mttr = current["mttr_seconds"]
    prev_mttr = previous["mttr_seconds"]

    fp_rate = current["fast_path_hit_rate_pct"]
    prev_fp_rate = previous["fast_path_hit_rate_pct"]

    return {
        "total_incidents": total,
        "auto_resolved_pct": round(auto_pct, 1),
        "success_failure_ratio": ratio_str,
        "mttr_seconds": mttr,
        "fast_path_hit_rate_pct": round(fp_rate, 1),
        "trends": {
            "total_incidents": trend(total, prev_total),
            "auto_resolved_pct": trend(auto_pct, prev_auto_pct),
            "success_failure_ratio": trend(ratio, prev_ratio),
            "mttr_seconds": trend(mttr, prev_mttr),
            "fast_path_hit_rate_pct": trend(fp_rate, prev_fp_rate),
        },
    }


async def _aggregate_period(
    conn: asyncpg.Connection | asyncpg.Pool,
    from_time: datetime,
    to_time: datetime,
) -> dict:
    """Compute aggregate metrics for a single time period."""
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE state = 'resolved') AS resolved,
            COUNT(*) FILTER (WHERE state = 'failed') AS failed,
            COUNT(*) FILTER (WHERE fast_path = TRUE) AS fast_path_count,
            COALESCE(
                EXTRACT(EPOCH FROM AVG(updated_at - created_at)
                    FILTER (WHERE state = 'resolved')),
                0
            )::int AS mttr_seconds
        FROM incidents
        WHERE created_at >= $1 AND created_at < $2
        """,
        from_time,
        to_time,
    )

    total = row["total"]
    resolved = row["resolved"]
    failed = row["failed"]
    fast_path_count = row["fast_path_count"]
    mttr_seconds = row["mttr_seconds"]

    auto_resolved_count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM incidents i
        WHERE i.created_at >= $1 AND i.created_at < $2
          AND i.state = 'resolved'
          AND NOT EXISTS (
              SELECT 1 FROM approval_records ar WHERE ar.incident_id = i.id
          )
        """,
        from_time,
        to_time,
    )

    auto_pct = (auto_resolved_count / total * 100) if total > 0 else 0.0
    fp_rate = (fast_path_count / total * 100) if total > 0 else 0.0

    return {
        "total_incidents": total,
        "resolved_count": resolved,
        "failed_count": failed,
        "auto_resolved_pct": auto_pct,
        "mttr_seconds": mttr_seconds,
        "fast_path_hit_rate_pct": fp_rate,
    }


async def get_timeseries_stats(
    conn: asyncpg.Connection | asyncpg.Pool,
    from_time: datetime,
    to_time: datetime,
    bucket_interval: str,
) -> dict:
    """Bucket incidents by time interval for chart data.

    Returns lists of timestamps and corresponding counts for alerts,
    diagnoses, resolutions, and MTTR per bucket.
    """
    rows = await conn.fetch(
        """
        WITH buckets AS (
            SELECT generate_series($1::timestamptz, $2::timestamptz, $3::interval) AS bucket_start
        )
        SELECT
            b.bucket_start,
            COUNT(i.id) AS alerts,
            COUNT(i.id) FILTER (WHERE i.state IN ('diagnosed', 'planning', 'awaiting_approval',
                'executing', 'observing', 'resolved', 'failed')) AS diagnoses,
            COUNT(i.id) FILTER (WHERE i.state = 'resolved') AS resolutions,
            COALESCE(
                EXTRACT(EPOCH FROM AVG(i.updated_at - i.created_at)
                    FILTER (WHERE i.state = 'resolved')),
                0
            )::int AS mttr_seconds
        FROM buckets b
        LEFT JOIN incidents i
            ON i.created_at >= b.bucket_start
            AND i.created_at < b.bucket_start + $3::interval
        GROUP BY b.bucket_start
        ORDER BY b.bucket_start
        """,
        from_time,
        to_time,
        bucket_interval,
    )

    last_bucket = from_time
    buckets = []
    alerts = []
    diagnoses = []
    resolutions = []
    mttr_seconds = []

    for row in rows:
        bucket_start = row["bucket_start"]
        if bucket_start >= to_time:
            break
        buckets.append(bucket_start.isoformat())
        alerts.append(row["alerts"])
        diagnoses.append(row["diagnoses"])
        resolutions.append(row["resolutions"])
        mttr_seconds.append(row["mttr_seconds"])

    return {
        "buckets": buckets,
        "alerts": alerts,
        "diagnoses": diagnoses,
        "resolutions": resolutions,
        "mttr_seconds": mttr_seconds,
    }
