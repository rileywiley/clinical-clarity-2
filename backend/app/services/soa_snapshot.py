"""SoA snapshot / restore (post-Phase-6).

A snapshot captures every Visit row across every Arm of a trial at a
moment in time. Restore writes those visits back onto the same arms,
after first taking a fresh snapshot of the current state (so restores
themselves are undoable).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.soa_snapshot import SoaSnapshot
from app.models.trial import Arm, Trial
from app.models.visit import Visit, VisitType


async def take_snapshot(
    db: AsyncSession,
    *,
    org_id: UUID,
    trial_id: UUID,
    reason: str,
    label: str | None,
    created_by_user_id: UUID | None,
) -> SoaSnapshot:
    """Snapshot every Visit row across every Arm of the given trial.

    ``reason`` must be one of "reparse_replace", "manual", "pre_restore"
    so the history panel can render an icon/label per snapshot.
    """
    arms = (
        await db.execute(select(Arm).where(Arm.trial_id == trial_id))
    ).scalars().all()
    arm_names = {a.id: a.name for a in arms}
    visits = (
        await db.execute(
            select(Visit).where(Visit.arm_id.in_(list(arm_names.keys() or [])))
        )
    ).scalars().all()
    payload: list[dict[str, Any]] = [
        {
            "arm_id": str(v.arm_id),
            "arm_name": arm_names.get(v.arm_id, ""),
            "name": v.name,
            "visit_type": v.visit_type.value,
            "target_day_offset": v.target_day_offset,
            "window_days": v.window_days,
            "duration_hours_override": (
                float(v.duration_hours_override)
                if v.duration_hours_override is not None
                else None
            ),
            "price": float(v.price) if v.price is not None else None,
            "cost": float(v.cost) if v.cost is not None else None,
            "sort_order": v.sort_order,
            "confidence": v.confidence,
            "flagged_reason": v.flagged_reason,
        }
        for v in visits
    ]
    snap = SoaSnapshot(
        org_id=org_id,
        trial_id=trial_id,
        created_by_user_id=created_by_user_id,
        reason=reason,
        label=label,
        visits=payload,
    )
    db.add(snap)
    await db.flush()
    return snap


async def restore_snapshot(
    db: AsyncSession,
    *,
    org_id: UUID,
    snapshot_id: UUID,
    user_id: UUID,
) -> SoaSnapshot:
    """Replace the trial's current SoA with the snapshot's. Takes a
    pre_restore snapshot first so users can undo a bad restore."""
    snap = await db.get(SoaSnapshot, snapshot_id)
    if snap is None or snap.org_id != org_id:
        raise ValueError("snapshot not found")

    trial = await db.get(Trial, snap.trial_id)
    if trial is None:
        raise ValueError("trial not found")

    # Safety net — undo a bad restore by restoring this auto-snapshot.
    await take_snapshot(
        db,
        org_id=org_id,
        trial_id=snap.trial_id,
        reason="pre_restore",
        label=f"auto-snapshot before restoring '{snap.label or snap.id}'",
        created_by_user_id=user_id,
    )

    # Replace.
    arms = (
        await db.execute(select(Arm).where(Arm.trial_id == snap.trial_id))
    ).scalars().all()
    arm_ids_by_name: dict[str, UUID] = {a.name: a.id for a in arms}

    existing_visits = (
        await db.execute(
            select(Visit).where(Visit.arm_id.in_([a.id for a in arms]))
        )
    ).scalars().all()
    for v in existing_visits:
        await db.delete(v)
    await db.flush()

    for spec in snap.visits:
        # Snapshots store arm names so they survive arm deletion + re-creation.
        # If the original arm name is gone (rare in single-arm trials), fall
        # back to the trial's first arm.
        arm_id = arm_ids_by_name.get(spec.get("arm_name", ""))
        if arm_id is None and arms:
            arm_id = arms[0].id
        if arm_id is None:
            continue
        db.add(
            Visit(
                org_id=org_id,
                arm_id=arm_id,
                name=spec["name"],
                visit_type=VisitType(spec["visit_type"]),
                target_day_offset=spec["target_day_offset"],
                window_days=spec.get("window_days", 0),
                duration_hours_override=spec.get("duration_hours_override"),
                price=spec.get("price"),
                cost=spec.get("cost"),
                sort_order=spec.get("sort_order", 0),
                confidence=spec.get("confidence"),
                flagged_reason=spec.get("flagged_reason"),
            )
        )
    await db.flush()
    return snap
