from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.org_settings import OrgSettings
from app.models.trial import Arm, Trial, TrialStatus
from app.models.user import User, UserRole
from app.schemas.arm import ArmIn, ArmOut, ArmPatch
from app.schemas.trial import (
    TrialActivationErrorOut,
    TrialActivationFailureOut,
    TrialIn,
    TrialOut,
    TrialPatch,
)
from app.services.trial_activation import validate_can_activate

router = APIRouter(prefix="/trials", tags=["trials"])

WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


# --- Trials --------------------------------------------------------------


@router.get("", response_model=list[TrialOut])
async def list_trials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Trial]:
    rows = (
        await db.execute(
            select(Trial).where(Trial.org_id == user.org_id).order_by(Trial.name)
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "",
    response_model=TrialOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_trial(
    payload: TrialIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trial:
    # Default the attrition curve to the org's Standard preset if the caller
    # didn't specify one (PRD §5.1).
    curve_id = payload.attrition_curve_id
    if curve_id is None:
        settings = (
            await db.execute(
                select(OrgSettings).where(OrgSettings.org_id == user.org_id)
            )
        ).scalar_one_or_none()
        if settings is not None:
            curve_id = settings.default_attrition_curve_id

    trial = Trial(
        org_id=user.org_id,
        name=payload.name,
        sponsor=payload.sponsor,
        protocol_ref=payload.protocol_ref,
        fpfv=payload.fpfv,
        lpfv=payload.lpfv,
        lplv=payload.lplv,
        is_multi_arm=payload.is_multi_arm,
        enrollment_target=payload.enrollment_target,
        screening_target=payload.screening_target,
        attrition_curve_id=curve_id,
    )
    db.add(trial)
    await db.flush()

    # Auto-create a Default Arm for single-arm trials so the UI never forces
    # arm-thinking (PRD §5.1).
    if not payload.is_multi_arm:
        db.add(Arm(org_id=user.org_id, trial_id=trial.id, name="Default Arm"))

    return trial


@router.get("/{trial_id}", response_model=TrialOut)
async def get_trial(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trial:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return t


@router.patch(
    "/{trial_id}",
    response_model=TrialOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def patch_trial(
    trial_id: UUID,
    payload: TrialPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trial:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    # Validate post-change date order.
    new_fpfv = updates.get("fpfv", t.fpfv)
    new_lpfv = updates.get("lpfv", t.lpfv)
    new_lplv = updates.get("lplv", t.lplv)
    if not (new_fpfv <= new_lpfv <= new_lplv):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="fpfv ≤ lpfv ≤ lplv must hold")
    for field, value in updates.items():
        setattr(t, field, value)
    return t


@router.post(
    "/{trial_id}/activate",
    response_model=TrialOut,
    responses={422: {"model": TrialActivationErrorOut}},
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def activate_trial(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trial:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if t.status is TrialStatus.ACTIVE:
        return t
    failures = await validate_can_activate(db, t)
    if failures:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "failures": [
                    TrialActivationFailureOut(reason=f.reason, detail=f.detail).model_dump()
                    for f in failures
                ]
            },
        )
    t.status = TrialStatus.ACTIVE
    return t


# --- Arms (nested under a trial) ----------------------------------------


@router.get("/{trial_id}/arms", response_model=list[ArmOut])
async def list_arms(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Arm]:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(select(Arm).where(Arm.trial_id == trial_id).order_by(Arm.name))
    ).scalars().all()
    return list(rows)


@router.post(
    "/{trial_id}/arms",
    response_model=ArmOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_arm(
    trial_id: UUID,
    payload: ArmIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Arm:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    arm = Arm(org_id=user.org_id, trial_id=trial_id, name=payload.name)
    db.add(arm)
    await db.flush()
    return arm


@router.patch(
    "/{trial_id}/arms/{arm_id}",
    response_model=ArmOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def patch_arm(
    trial_id: UUID,
    arm_id: UUID,
    payload: ArmPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Arm:
    a = await db.get(Arm, arm_id)
    if a is None or a.org_id != user.org_id or a.trial_id != trial_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(a, field, value)
    return a
