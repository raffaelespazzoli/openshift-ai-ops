"""Shared test fixtures for the openshift-ai-ops backend.

Provides:
- Session-scoped PostgreSQL container via testcontainers (pgvector/pgvector:pg18)
- Alembic migrations run in fixture setup
- Per-test async database connection with rollback isolation
- FastAPI TestClient backed by the test database
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

import asyncpg
import httpx
import pytest
from sqlalchemy.engine.url import URL

try:
    from testcontainers.community.postgres import PostgresContainer
except ImportError:
    from testcontainers.postgres import PostgresContainer

_TEST_USERNAME = "test"
_TEST_PASSWORD = "test"
_TEST_DBNAME = "test_db"


def _make_url(
    postgres_container: PostgresContainer,
    drivername: str = "postgresql",
) -> URL:
    """Build a SQLAlchemy URL from container connection details."""
    return URL.create(
        drivername=drivername,
        username=_TEST_USERNAME,
        password=_TEST_PASSWORD,
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(5432)),
        database=_TEST_DBNAME,
    )


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Spin up a PostgreSQL 18 + pgvector container for the test session."""
    with PostgresContainer(
        "pgvector/pgvector:pg18",
        username=_TEST_USERNAME,
        password=_TEST_PASSWORD,
        dbname=_TEST_DBNAME,
        driver=None,
    ) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def db_url(postgres_container: PostgresContainer) -> str:
    """Get the database URL from the running container."""
    return _make_url(postgres_container).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def sqlalchemy_url(postgres_container: PostgresContainer) -> str:
    """Get the SQLAlchemy-compatible URL (uses psycopg3 driver)."""
    return _make_url(postgres_container, drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )


@pytest.fixture(scope="session")
def run_migrations(sqlalchemy_url: str) -> None:
    """Run Alembic migrations against the test database."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
async def db_conn(db_url: str, run_migrations: None) -> AsyncGenerator[asyncpg.Connection, None]:
    """Provide a per-test connection wrapped in a transaction for isolation."""
    conn = await asyncpg.connect(db_url)
    tx = conn.transaction()
    await tx.start()
    yield conn
    await tx.rollback()
    await conn.close()


@pytest.fixture
async def async_client(
    postgres_container: PostgresContainer, run_migrations: None
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide a FastAPI TestClient backed by the test database."""
    url = _make_url(postgres_container)

    os.environ["POSTGRES_HOST"] = url.host or "localhost"
    os.environ["POSTGRES_PORT"] = str(url.port or 5432)
    os.environ["POSTGRES_USER"] = url.username or ""
    os.environ["POSTGRES_PASSWORD"] = url.password or ""
    os.environ["POSTGRES_DB"] = url.database or ""

    import importlib
    import src.db.connection as db_mod
    db_mod._pool = None
    importlib.reload(db_mod)

    from src.api.app import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
