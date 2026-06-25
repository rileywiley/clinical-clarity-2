"""SoA snapshots (post-Phase-6).

  GET   /trials/{trial_id}/soa-snapshots
  POST  /trials/{trial_id}/soa-snapshots            (manual snapshot)
  POST  /soa-snapshots/{snapshot_id}/restore

Auto snapshots (reason="reparse_replace" / "pre_restore") are written
by the apply-parse-job endpoint and the restore route, respectively —
no public endpoint creates them.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.soa_snapshot import SoaSnapshot
from app.models.trial import Trial
from app.models.user import User, UserRole
from app.services.soa_snapshot import restore_snapshot, take_snapshot

router = APIRouter(tags=["soa-snapshots"])
WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


class SnapshotOut(BaseModel):
    id: UUID
    trial_id: UUID
    reason: str
    label: str | None
    created_at: str
    visit_count: int


class ManualSnapshotIn(BaseModel):
    label: str | None = None


def _to_out(snap: SoaSnapshot) -> SnapshotOut:
    return SnapshotOut(
        id=snap.id,
        trial_id=snap.trial_id,
        reason=snap.reason,
        label=snap.label,
        created_at=snap.created_at.isoformat() if snap.created_at else "",
        visit_count=len(snap.visits),
    )


@router.get(
    "/trials/{trial_id}/soa-snapshots",
    response_model=list[SnapshotOut],
)
async def list_snapshots(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SnapshotOut]:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(
            select(SoaSnapshot)
            .where(SoaSnapshot.trial_id == trial_id)
            .order_by(SoaSnapshot.created_at.desc())
        )
    ).scalars().all()
    return [_to_out(s) for s in rows]


@router.post(
    "/trials/{trial_id}/soa-snapshots",
    response_model=SnapshotOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_manual_snapshot(
    trial_id: UUID,
    payload: ManualSnapshotIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SnapshotOut:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    snap = await take_snapshot(
        db,
        org_id=user.org_id,
        trial_id=trial_id,
        reason="manual",
        label=payload.label,
        created_by_user_id=user.id,
    )
    return _to_out(snap)


@router.post(
    "/soa-snapshots/{snapshot_id}/restore",
    response_model=SnapshotOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def restore(
    snapshot_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SnapshotOut:
    snap = await db.get(SoaSnapshot, snapshot_id)
    if snap is None or snap.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await restore_snapshot(
        db,
        org_id=user.org_id,
        snapshot_id=snapshot_id,
        user_id=user.id,
    )
    return _to_out(snap)
