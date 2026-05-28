from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.trial import Arm
from app.models.user import User, UserRole
from app.models.visit import Visit
from app.schemas.visit import VisitIn, VisitOut, VisitPatch

router = APIRouter(prefix="/arms", tags=["visits"])


WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


async def _ensure_arm(db: AsyncSession, user: User, arm_id: UUID) -> Arm:
    a = await db.get(Arm, arm_id)
    if a is None or a.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return a


@router.get("/{arm_id}/visits", response_model=list[VisitOut])
async def list_visits(
    arm_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Visit]:
    await _ensure_arm(db, user, arm_id)
    rows = (
        await db.execute(
            select(Visit).where(Visit.arm_id == arm_id).order_by(Visit.sort_order, Visit.target_day_offset)
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/{arm_id}/visits",
    response_model=VisitOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_visit(
    arm_id: UUID,
    payload: VisitIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Visit:
    await _ensure_arm(db, user, arm_id)
    visit = Visit(
        org_id=user.org_id,
        arm_id=arm_id,
        name=payload.name,
        visit_type=payload.visit_type,
        target_day_offset=payload.target_day_offset,
        window_days=payload.window_days,
        duration_hours_override=payload.duration_hours_override,
        price=payload.price,
        cost=payload.cost,
        sort_order=payload.sort_order,
    )
    db.add(visit)
    await db.flush()
    return visit


@router.patch(
    "/{arm_id}/visits/{visit_id}",
    response_model=VisitOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def patch_visit(
    arm_id: UUID,
    visit_id: UUID,
    payload: VisitPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Visit:
    v = await db.get(Visit, visit_id)
    if v is None or v.org_id != user.org_id or v.arm_id != arm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(v, field, value)
    return v


@router.delete(
    "/{arm_id}/visits/{visit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def delete_visit(
    arm_id: UUID,
    visit_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    v = await db.get(Visit, visit_id)
    if v is None or v.org_id != user.org_id or v.arm_id != arm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await db.delete(v)
