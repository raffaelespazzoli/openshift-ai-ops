"""Database module — asyncpg connection management and persistence."""

from .connection import close_pool, get_db_url, get_pool
from .correlation import (
    add_alert_to_group,
    check_dedup,
    create_correlation_group,
    get_groups_to_seal,
    get_open_groups,
    seal_group,
    update_dedup_timestamp,
)
from .incidents import create_alert, create_incident, record_resolved_alert

__all__ = [
    "add_alert_to_group",
    "check_dedup",
    "close_pool",
    "create_alert",
    "create_correlation_group",
    "create_incident",
    "get_db_url",
    "get_groups_to_seal",
    "get_open_groups",
    "get_pool",
    "record_resolved_alert",
    "seal_group",
    "update_dedup_timestamp",
]
