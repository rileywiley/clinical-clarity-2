"""User management + site assignments (PRD §3, §7.5, §8.6).

Admin-only — these endpoints are gated to Org Admin. RLS ensures cross-org
isolation regardless of the role check (defense in depth).

Site assignments live on a separate endpoint surface (`/sites/{id}/users`)
so the Admin Settings page can render a per-site user table without first
loading every user in the org.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.site import Site
from app.models.user import User, UserRole
from app.models.user_site_assignment import UserSiteAssignment
from app.schemas.users import (
    SiteUserAssignmentIn,
    SiteUserOut,
    UserCreateIn,
    UserOut,
    UserPatchIn,
)
from app.security import hash_password

router = APIRouter(tags=["users"])

ADMIN_ONLY = require_role(UserRole.ORG_ADMIN)


# --- User CRUD --------------------------------------------------------


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(ADMIN_ONLY)])
async def list_users(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    rows = (
        await db.execute(
            select(User).where(User.org_id == user.org_id).order_by(User.name)
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ADMIN_ONLY)],
)
async def create_user(
    payload: UserCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = (
        await db.execute(
            select(User).where(User.org_id == user.org_id, User.email == payload.email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="a user with this email already exists in this org"
        )
    new_user = User(
        org_id=user.org_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
    )
    db.add(new_user)
    await db.flush()
    return new_user


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(ADMIN_ONLY)],
)
async def patch_user(
    user_id: UUID,
    payload: UserPatchIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    target = await db.get(User, user_id)
    if target is None or target.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # Don't let an admin lock themselves out — refuse role changes / deactivation
    # of the calling user if they're the only active admin.
    if target.id == user.id and (
        (payload.role is not None and payload.role is not UserRole.ORG_ADMIN)
        or payload.active is False
    ):
        admin_count = len(
            (
                await db.execute(
                    select(User).where(
                        User.org_id == user.org_id,
                        User.role == UserRole.ORG_ADMIN,
                        User.active.is_(True),
                    )
                )
            ).scalars().all()
        )
        if admin_count <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="cannot remove the last active Org Admin",
            )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    return target


# --- Site assignments -------------------------------------------------


@router.get(
    "/sites/{site_id}/users",
    response_model=list[SiteUserOut],
)
async def list_site_users(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SiteUserOut]:
    """Users currently assigned to this site. Visible to anyone who can see the
    site (i.e. anyone in the org); only writes are admin-gated."""
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(
            select(UserSiteAssignment, User)
            .join(User, User.id == UserSiteAssignment.user_id)
            .where(UserSiteAssignment.site_id == site_id)
            .order_by(User.name)
        )
    ).all()
    return [
        SiteUserOut(
            assignment_id=a.id,
            user_id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
        )
        for a, u in rows
    ]


@router.post(
    "/sites/{site_id}/users",
    response_model=SiteUserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ADMIN_ONLY)],
)
async def assign_user_to_site(
    site_id: UUID,
    payload: SiteUserAssignmentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteUserOut:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="site not found")
    target = await db.get(User, payload.user_id)
    if target is None or target.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user not found")

    existing = (
        await db.execute(
            select(UserSiteAssignment).where(
                UserSiteAssignment.site_id == site_id,
                UserSiteAssignment.user_id == payload.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="user is already assigned to this site"
        )

    assignment = UserSiteAssignment(
        org_id=user.org_id,
        user_id=payload.user_id,
        site_id=site_id,
    )
    db.add(assignment)
    await db.flush()
    return SiteUserOut(
        assignment_id=assignment.id,
        user_id=target.id,
        email=target.email,
        name=target.name,
        role=target.role,
    )


@router.delete(
    "/sites/{site_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(ADMIN_ONLY)],
)
async def unassign_user_from_site(
    site_id: UUID,
    user_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    assignment = (
        await db.execute(
            select(UserSiteAssignment).where(
                UserSiteAssignment.site_id == site_id,
                UserSiteAssignment.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="assignment not found")
    await db.delete(assignment)
