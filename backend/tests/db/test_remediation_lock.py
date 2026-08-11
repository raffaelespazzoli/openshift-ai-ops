"""DB integration tests for remediation lock (Story 3.5, AD-18).

Tests: acquire lock, second acquire fails (NOWAIT), release + re-acquire,
connection drop releases lock.
"""

import uuid
from datetime import datetime, timezone

import asyncpg
import pytest

from src.db.remediation_lock import (
    acquire_remediation_lock,
    is_lock_held,
    release_remediation_lock,
)

pytestmark = pytest.mark.db


async def _seed_incident(conn):
    """Insert minimal incident for lock FK."""
    incident_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await conn.execute(
        "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, 'executing', 'critical', $2, $3)",
        incident_id, now, now,
    )
    return incident_id


class TestAcquireLock:
    """Global remediation lock acquisition tests."""

    async def test_acquire_succeeds_first_time(self, db_conn):
        incident_id = await _seed_incident(db_conn)
        acquired = await acquire_remediation_lock(db_conn, incident_id)
        assert acquired is True

    async def test_lock_held_after_acquire(self, db_conn):
        incident_id = await _seed_incident(db_conn)
        await acquire_remediation_lock(db_conn, incident_id)
        held = await is_lock_held(db_conn)
        assert held is True

    async def test_second_acquire_on_same_connection_succeeds(self, db_conn):
        incident_id = await _seed_incident(db_conn)
        await acquire_remediation_lock(db_conn, incident_id)
        acquired = await acquire_remediation_lock(db_conn, incident_id)
        assert acquired is True


class TestLockContention:
    """Lock contention via two connections (requires committed data)."""

    async def test_second_connection_fails_nowait(self, db_url, run_migrations):
        conn1 = await asyncpg.connect(db_url)
        conn2 = await asyncpg.connect(db_url)

        try:
            incident_id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            await conn1.execute(
                "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, 'executing', 'critical', $2, $3)",
                incident_id, now, now,
            )

            tx1 = conn1.transaction()
            await tx1.start()
            acquired1 = await acquire_remediation_lock(conn1, incident_id)
            assert acquired1 is True

            tx2 = conn2.transaction()
            await tx2.start()
            acquired2 = await acquire_remediation_lock(conn2, incident_id)
            assert acquired2 is False

            await tx2.rollback()
            await tx1.rollback()

            await conn1.execute("DELETE FROM incidents WHERE id = $1", incident_id)
        finally:
            await conn1.close()
            await conn2.close()

    async def test_release_and_reacquire(self, db_url, run_migrations):
        conn1 = await asyncpg.connect(db_url)
        conn2 = await asyncpg.connect(db_url)

        try:
            incident_id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            await conn1.execute(
                "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, 'executing', 'critical', $2, $3)",
                incident_id, now, now,
            )

            tx1 = conn1.transaction()
            await tx1.start()
            acquired1 = await acquire_remediation_lock(conn1, incident_id)
            assert acquired1 is True

            await release_remediation_lock(conn1)
            await tx1.commit()

            tx2 = conn2.transaction()
            await tx2.start()
            acquired2 = await acquire_remediation_lock(conn2, incident_id)
            assert acquired2 is True
            await tx2.rollback()

            await conn1.execute("DELETE FROM incidents WHERE id = $1", incident_id)
        finally:
            await conn1.close()
            await conn2.close()


class TestLockConnectionDrop:
    """Connection drop releases the lock."""

    async def test_connection_close_releases_lock(self, db_url, run_migrations):
        conn1 = await asyncpg.connect(db_url)
        conn2 = await asyncpg.connect(db_url)

        try:
            incident_id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            await conn1.execute(
                "INSERT INTO incidents (id, state, severity, created_at, updated_at) VALUES ($1, 'executing', 'critical', $2, $3)",
                incident_id, now, now,
            )

            tx1 = conn1.transaction()
            await tx1.start()
            await acquire_remediation_lock(conn1, incident_id)

            await conn1.close()

            tx2 = conn2.transaction()
            await tx2.start()
            acquired2 = await acquire_remediation_lock(conn2, incident_id)
            assert acquired2 is True
            await tx2.rollback()

            await conn2.execute("DELETE FROM incidents WHERE id = $1", incident_id)
        finally:
            if not conn2.is_closed():
                await conn2.close()
