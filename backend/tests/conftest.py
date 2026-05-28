"""Test fixtures.

Strategy: a single Postgres instance, but each test gets a private database created
fresh by the session-scoped DB fixture. This keeps tests isolated without needing
transactional rollback gymnastics that would conflict with RLS's reliance on
``SET LOCAL``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command

# --- Test DB lifecycle ------------------------------------------------------

PG_SUPERUSER_URL = os.environ.get(
    "TEST_PG_SUPERUSER_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
PG_HOST = os.environ.get("PGHOST", "localhost")
PG_PORT = os.environ.get("PGPORT", "55432")


def _superuser_psql(sql: str, db: str = "postgres") -> None:
    """Run a SQL statement as the Postgres superuser via psql.

    We use psql rather than asyncpg for these DDL statements because CREATE/DROP
    DATABASE can't run inside a transaction block, and psql handles that cleanly.
    """
    env = {
        **os.environ,
        "PGPASSWORD": os.environ.get("PGPASSWORD", "postgres"),
    }
    subprocess.run(
        [
            "psql",
            "-h",
            PG_HOST,
            "-p",
            PG_PORT,
            "-U",
            os.environ.get("PGUSER", "postgres"),
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        check=True,
        env=env,
        capture_output=True,
    )


def _superuser_psql_file(path: Path, db: str) -> None:
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "postgres")}
    subprocess.run(
        [
            "psql",
            "-h",
            PG_HOST,
            "-p",
            PG_PORT,
            "-U",
            os.environ.get("PGUSER", "postgres"),
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(path),
        ],
        check=True,
        env=env,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_db_name() -> str:
    return f"vfp_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database(test_db_name: str) -> Iterator[None]:
    """Create a fresh DB, ensure roles exist, run migrations once for the session."""
    # Roles are created idempotently — local dev already has them; CI creates them
    # via the bootstrap step. Either way, we just verify they exist before going on.
    _superuser_psql(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_owner') THEN "
        "    CREATE ROLE app_owner WITH LOGIN PASSWORD 'app_owner_pw' BYPASSRLS; "
        "  END IF; "
        "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_user') THEN "
        "    CREATE ROLE app_user WITH LOGIN PASSWORD 'app_user_pw'; "
        "  END IF; "
        "END $$;"
    )

    _superuser_psql(f'CREATE DATABASE "{test_db_name}" OWNER app_owner')
    _superuser_psql(f'GRANT CONNECT ON DATABASE "{test_db_name}" TO app_user', db=test_db_name)
    _superuser_psql("ALTER SCHEMA public OWNER TO app_owner", db=test_db_name)
    _superuser_psql("GRANT USAGE ON SCHEMA public TO app_user", db=test_db_name)

    # Point app config at the fresh DB before importing the app modules.
    admin_url = f"postgresql+asyncpg://app_owner:app_owner_pw@{PG_HOST}:{PG_PORT}/{test_db_name}"
    user_url = f"postgresql+asyncpg://app_user:app_user_pw@{PG_HOST}:{PG_PORT}/{test_db_name}"
    os.environ["DATABASE_URL"] = user_url
    os.environ["DATABASE_URL_ADMIN"] = admin_url
    os.environ["SESSION_SECRET"] = "test-secret"

    # Run migrations under app_owner.
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", admin_url)
    command.upgrade(cfg, "head")

    yield

    _superuser_psql(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)')


@pytest_asyncio.fixture
async def truncate_between_tests() -> AsyncIterator[None]:
    """Wipe tenant data between tests so they don't see each other."""
    from app.config import get_settings  # imported lazily so env vars are picked up

    settings = get_settings()
    engine = create_async_engine(settings.database_url_admin, poolclass=None)
    async with engine.begin() as conn:
        # CASCADE drops every org-scoped row via the org_id FK ON DELETE CASCADE
        # chain, so we only need to name the tenant roots explicitly.
        await conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))
    await engine.dispose()
    yield


# --- App + client fixtures --------------------------------------------------


@pytest_asyncio.fixture
async def client(truncate_between_tests: None) -> AsyncIterator[AsyncClient]:
    # Re-import so the app picks up the test DSN from the env.
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()  # type: ignore[attr-defined]
    # Reset cached engine/sessionmaker so a new one is built against the test DB.
    from app import db as db_module

    db_module._engine = None
    db_module._sessionmaker = None

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    from app.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    engine = create_async_engine(get_settings().database_url_admin)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def user_engine() -> AsyncIterator[AsyncEngine]:
    from app.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()
