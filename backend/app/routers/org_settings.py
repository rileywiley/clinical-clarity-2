"""Admin-only API for OrgSettings (PRD §7.5 / §8.6).

Changes here re-flow live (PRD §5.2): the resolution service reads OrgSettings
on each forecast/render, so a PATCH takes effect on the next render.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.org_settings import OrgSettings
from app.models.user import User, UserRole
from app.schemas.org_settings import OrgSettingsOut, OrgSettingsPatch

router = APIRouter(prefix="/org-settings", tags=["org-settings"])


@router.get("", response_model=OrgSettingsOut)
async def get_my_org_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgSettings:
    s = (
        await db.execute(select(OrgSettings).where(OrgSettings.org_id == user.org_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="org_settings missing")
    return s


@router.patch(
    "",
    response_model=OrgSettingsOut,
    dependencies=[Depends(require_role(UserRole.ORG_ADMIN))],
)
async def patch_my_org_settings(
    payload: OrgSettingsPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgSettings:
    s = (
        await db.execute(select(OrgSettings).where(OrgSettings.org_id == user.org_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="org_settings missing")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    return s
