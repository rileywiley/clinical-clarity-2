"""Async SQLAlchemy engine + per-request session.

Every request opens a session, sets the tenant context for RLS, and commits or rolls
back on exit. The runtime engine connects as ``app_user``, which is subject to RLS.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def set_tenant(session: AsyncSession, org_id: UUID | None) -> None:
    """Bind the current tenant for RLS policies.

    Postgres RLS policies read ``current_setting('app.current_org_id', true)`` and
    compare it to each row's ``org_id``. Using SET LOCAL keeps this scoped to the
    current transaction, so requests can't leak tenant context to each other.
    """
    if org_id is None:
        # Clear by setting to empty string. Policies treat NULL setting as "no access"
        # to org-scoped tables.
        await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    else:
        await session.execute(
            text("SELECT set_config('app.current_org_id', :v, true)"),
            {"v": str(org_id)},
        )


@asynccontextmanager
async def session_scope(org_id: UUID | None = None) -> AsyncIterator[AsyncSession]:
    """Context manager for ad-hoc session use (CLI, tests, startup hooks)."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await set_tenant(session, org_id)
        yield session
