from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.attrition_curve import AttritionCurve
from app.models.user import User, UserRole
from app.schemas.attrition_curve import (
    AttritionCurveIn,
    AttritionCurveOut,
    AttritionCurvePatch,
)

router = APIRouter(prefix="/attrition-curves", tags=["attrition-curves"])


@router.get("", response_model=list[AttritionCurveOut])
async def list_curves(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttritionCurve]:
    rows = (
        await db.execute(
            select(AttritionCurve)
            .where(
                or_(
                    AttritionCurve.org_id == user.org_id,
                    AttritionCurve.org_id.is_(None),
                )
            )
            .order_by(AttritionCurve.total_dropout_pct)
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "",
    response_model=AttritionCurveOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ORG_ADMIN))],
)
async def create_curve(
    payload: AttritionCurveIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttritionCurve:
    curve = AttritionCurve(
        org_id=user.org_id,
        name=payload.name,
        total_dropout_pct=payload.total_dropout_pct,
        shape=payload.shape,
        is_preset=False,
    )
    db.add(curve)
    await db.flush()
    return curve


@router.patch(
    "/{curve_id}",
    response_model=AttritionCurveOut,
    dependencies=[Depends(require_role(UserRole.ORG_ADMIN))],
)
async def patch_curve(
    curve_id: UUID,
    payload: AttritionCurvePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttritionCurve:
    c = await db.get(AttritionCurve, curve_id)
    if c is None or c.org_id != user.org_id:
        # Global seeds (org_id is None) are immutable from the API in v1.
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    return c
