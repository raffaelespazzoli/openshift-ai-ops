"""Database integration tests — verify migrations create expected schema."""

import pytest


@pytest.mark.db
async def test_migrations_create_incidents_table(db_conn):
    """Verify the incidents table exists after migration."""
    result = await db_conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'incidents')"
    )
    assert result is True


@pytest.mark.db
async def test_migrations_create_alerts_table(db_conn):
    """Verify the alerts table exists after migration."""
    result = await db_conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alerts')"
    )
    assert result is True


@pytest.mark.db
async def test_migrations_create_audit_log_table(db_conn):
    """Verify the audit_log table exists after migration."""
    result = await db_conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'audit_log')"
    )
    assert result is True


@pytest.mark.db
async def test_pgvector_extension_active(db_conn):
    """Verify pgvector extension is installed."""
    result = await db_conn.fetchval(
        "SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector')"
    )
    assert result is True


@pytest.mark.db
async def test_no_langgraph_tables(db_conn):
    """Verify no langgraph_* tables are created (AD-3)."""
    result = await db_conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'langgraph%'"
    )
    assert len(result) == 0
