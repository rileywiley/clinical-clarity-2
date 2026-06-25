from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.enrollment_week import EnrollmentWeek
from app.models.site import Site
from app.models.site_trial import SiteTrial
from app.models.user import User, UserRole
from app.models.user_site_assignment import UserSiteAssignment
from app.schemas.site import SiteIn, SiteOut, SitePatch

router = APIRouter(prefix="/sites", tags=["sites"])


WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


@router.get("", response_model=list[SiteOut])
async def list_sites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Site]:
    rows = (
        await db.execute(select(Site).where(Site.org_id == user.org_id).order_by(Site.name))
    ).scalars().all()
    return list(rows)


@router.post(
    "",
    response_model=SiteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_site(
    payload: SiteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Site:
    site = Site(
        org_id=user.org_id,
        name=payload.name,
        address=payload.address,
        timezone=payload.timezone,
        operating_weekdays=payload.operating_weekdays,
        hours_per_day=payload.hours_per_day,
        rooms=payload.rooms,
        active=payload.active,
    )
    db.add(site)
    await db.flush()
    return site


@router.get("/{site_id}", response_model=SiteOut)
async def get_site(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Site:
    s = await db.get(Site, site_id)
    if s is None or s.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return s


@router.patch(
    "/{site_id}",
    response_model=SiteOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def patch_site(
    site_id: UUID,
    payload: SitePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Site:
    s = await db.get(Site, site_id)
    if s is None or s.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    return s


class SiteDeleteImpactOut(BaseModel):
    """Counts of dependents a DELETE on this site would cascade to.
    Surfaced to the UI so the user sees what they're about to wipe."""

    site_name: str
    trial_assignments: int
    enrollment_weeks: int
    user_assignments: int


@router.get(
    "/{site_id}/delete-impact",
    response_model=SiteDeleteImpactOut,
)
async def site_delete_impact(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteDeleteImpactOut:
    s = await db.get(Site, site_id)
    if s is None or s.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    trial_assignments = (
        await db.execute(
            select(func.count(SiteTrial.id)).where(SiteTrial.site_id == site_id)
        )
    ).scalar_one()
    enrollment_weeks = (
        await db.execute(
            select(func.count(EnrollmentWeek.id)).where(
                EnrollmentWeek.site_id == site_id
            )
        )
    ).scalar_one()
    user_assignments = (
        await db.execute(
            select(func.count(UserSiteAssignment.id)).where(
                UserSiteAssignment.site_id == site_id
            )
        )
    ).scalar_one()
    return SiteDeleteImpactOut(
        site_name=s.name,
        trial_assignments=trial_assignments,
        enrollment_weeks=enrollment_weeks,
        user_assignments=user_assignments,
    )


@router.delete(
    "/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ORG_ADMIN))],
)
async def delete_site(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    s = await db.get(Site, site_id)
    if s is None or s.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await db.delete(s)
