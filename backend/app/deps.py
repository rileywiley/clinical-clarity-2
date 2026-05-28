"""FastAPI dependencies — DB session w/ tenant binding, current user, role gate."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker, set_tenant
from app.models.user import User, UserRole
from app.security import deserialize_session


async def get_db_unscoped() -> AsyncIterator[AsyncSession]:
    """Session without tenant binding. Used only for login (which needs to look up
    the user before we know which org to bind) and signup (which creates the org)."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        yield session


async def _session_token_from_cookie() -> None:  # placeholder for typing
    raise NotImplementedError


def session_cookie() -> str:
    return get_settings().session_cookie_name


async def get_current_user(
    db_unscoped: AsyncSession = Depends(get_db_unscoped),
    session_token: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> User:
    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    payload = deserialize_session(session_token)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid session")

    user_id = UUID(payload["user_id"])
    org_id = UUID(payload["org_id"])

    # Bind tenant before reading the user — defense-in-depth: even this lookup
    # is RLS-enforced under the runtime role.
    await set_tenant(db_unscoped, org_id)
    user = (await db_unscoped.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.active or user.org_id != org_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    return user


async def get_db(user: User = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped session for authenticated requests. The session is already
    bound to the user's org via get_current_user; we yield it for the route to use."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await set_tenant(session, user.org_id)
        yield session


def require_role(*allowed: UserRole):
    """Dep factory: 403 unless the current user has one of the allowed roles."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"role {user.role.value} not permitted",
            )
        return user

    return _checker
