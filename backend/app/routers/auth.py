from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import set_tenant
from app.deps import get_current_user, get_db_unscoped
from app.models.user import User
from app.schemas.auth import LoginIn, MeOut
from app.security import serialize_session, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(
    payload: LoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db_unscoped),
) -> Response:
    # The client tells us which org to authenticate against. We bind that as the
    # tenant context so the user lookup can read its row under RLS. A wrong
    # org_id just returns "invalid credentials" — UUIDs aren't enumerable.
    await set_tenant(db, payload.org_id)

    user = (
        await db.execute(
            select(User).where(
                User.org_id == payload.org_id,
                User.email == payload.email,
                User.active.is_(True),
            )
        )
    ).scalar_one_or_none()

    # Same response for "no user" and "wrong password" so we don't leak existence.
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    token = serialize_session(user.id, user.org_id)
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        domain=settings.session_cookie_domain,
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
