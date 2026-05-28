from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.site import Site
from app.models.site_trial import SiteTrial, SiteTrialVisitOverride
from app.models.trial import Trial
from app.models.user import User, UserRole
from app.models.visit import Visit
from app.schemas.site_trial import (
    SiteTrialIn,
    SiteTrialOut,
    SiteTrialPatch,
    VisitOverrideIn,
    VisitOverrideOut,
)

router = APIRouter(tags=["site-trials"])

WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


# --- assignments under /trials/{trial_id}/sites -------------------------


@router.get("/trials/{trial_id}/sites", response_model=list[SiteTrialOut])
async def list_assignments(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SiteTrial]:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(select(SiteTrial).where(SiteTrial.trial_id == trial_id))
    ).scalars().all()
    return list(rows)


@router.post(
    "/trials/{trial_id}/sites",
    response_model=SiteTrialOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def assign_site(
    trial_id: UUID,
    payload: SiteTrialIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteTrial:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    s = await db.get(Site, payload.site_id)
    if s is None or s.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="site not found")

    st = SiteTrial(
        org_id=user.org_id,
        site_id=payload.site_id,
        trial_id=trial_id,
        per_site_enrollment_target=payload.per_site_enrollment_target,
        per_site_screening_target=payload.per_site_screening_target,
        active=payload.active,
    )
    db.add(st)
    await db.flush()
    return st


@router.patch(
    "/site-trials/{site_trial_id}",
    response_model=SiteTrialOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def patch_assignment(
    site_trial_id: UUID,
    payload: SiteTrialPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SiteTrial:
    st = await db.get(SiteTrial, site_trial_id)
    if st is None or st.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(st, field, value)
    return st


# --- per-site visit overrides under /site-trials/{id}/visit-overrides ---


@router.get(
    "/site-trials/{site_trial_id}/visit-overrides",
    response_model=list[VisitOverrideOut],
)
async def list_overrides(
    site_trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SiteTrialVisitOverride]:
    st = await db.get(SiteTrial, site_trial_id)
    if st is None or st.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(
            select(SiteTrialVisitOverride).where(
                SiteTrialVisitOverride.site_trial_id == site_trial_id
            )
        )
    ).scalars().all()
    return list(rows)


@router.put(
    "/site-trials/{site_trial_id}/visit-overrides",
    response_model=list[VisitOverrideOut],
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def replace_overrides(
    site_trial_id: UUID,
    payload: list[VisitOverrideIn],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SiteTrialVisitOverride]:
    """Replace the whole override set for a site-trial. Simpler than POST/DELETE
    pairs and matches how the trial setup wizard (Phase 5) will save edits."""
    st = await db.get(SiteTrial, site_trial_id)
    if st is None or st.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    # Validate every visit belongs to this trial's arms (defense in depth — RLS
    # already blocks cross-org, but we still want a clean 422 for cross-trial).
    if payload:
        visit_ids = [o.visit_id for o in payload]
        rows = (
            await db.execute(select(Visit).where(Visit.id.in_(visit_ids)))
        ).scalars().all()
        if len(rows) != len(set(visit_ids)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="visit not found")
        # Org-scope check (RLS handles, but explicit is clearer).
        for v in rows:
            if v.org_id != user.org_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND)

    # Wipe existing and insert fresh.
    existing = (
        await db.execute(
            select(SiteTrialVisitOverride).where(
                SiteTrialVisitOverride.site_trial_id == site_trial_id
            )
        )
    ).scalars().all()
    for o in existing:
        await db.delete(o)
    await db.flush()

    new_rows: list[SiteTrialVisitOverride] = []
    for spec in payload:
        o = SiteTrialVisitOverride(
            org_id=user.org_id,
            site_trial_id=site_trial_id,
            visit_id=spec.visit_id,
            duration_hours=spec.duration_hours,
        )
        db.add(o)
        new_rows.append(o)
    await db.flush()
    return new_rows
