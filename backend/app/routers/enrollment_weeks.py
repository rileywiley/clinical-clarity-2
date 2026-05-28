"""Projections & actuals API (PRD §7.3).

Surface:
- GET  /site-trials/{id}/enrollment-weeks?from=&to=&arm_id=  → rows in range,
       zero-projection rows backfilled so the grid can render a complete grid
       without the frontend having to know the calendar.
- PUT  /site-trials/{id}/enrollment-weeks                    → bulk replace.
       Past projection edits are rejected with 409 (hard lock per saved memory).
- GET  /site-trials/{id}/enrollment-weeks/history            → audit trail.
- GET  /trials/{id}/variance                                 → warn-and-allow
       running variance against trial targets.

Past = ``week_start < monday_of(today)`` in the *site's* local timezone. v1
uses Python's ``date.today()`` as a proxy — the engine and metrics already use
the same proxy. A future change to site-tz-aware "today" would land in one
place (`_today_monday_for_site`).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.enrollment_week import EnrollmentWeek, EnrollmentWeekHistory
from app.models.site_trial import SiteTrial
from app.models.trial import Arm, Trial
from app.models.user import User, UserRole
from app.schemas.enrollment_week import (
    EnrollmentWeekHistoryOut,
    EnrollmentWeekOut,
    EnrollmentWeeksBulkIn,
    TrialVarianceOut,
)
from app.services.enrollment_audit import diff_projection_fields
from app.services.enrollment_variance import compute_trial_variance

router = APIRouter(tags=["enrollment-weeks"])

WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD, UserRole.SITE_MANAGER)


def _site_local_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _ensure_site_trial(
    db: AsyncSession, user: User, site_trial_id: UUID
) -> SiteTrial:
    st = await db.get(SiteTrial, site_trial_id)
    if st is None or st.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return st


# --- GET (grid load) ----------------------------------------------------


@router.get(
    "/site-trials/{site_trial_id}/enrollment-weeks",
    response_model=list[EnrollmentWeekOut],
)
async def list_enrollment_weeks(
    site_trial_id: UUID,
    arm_id: UUID,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentWeek]:
    """Return persisted rows for the (site, trial, arm) in ``[from, to]``, padded
    with zero-projection rows for weeks the user hasn't touched yet so the grid
    can render a complete calendar.

    Padded rows are *not* persisted — they're plain dicts shaped like
    EnrollmentWeekOut. Pydantic's from_attributes mode handles real ORM rows;
    the padding dicts go through model_validate.
    """
    st = await _ensure_site_trial(db, user, site_trial_id)

    # Validate the arm belongs to the same trial.
    arm = await db.get(Arm, arm_id)
    if arm is None or arm.org_id != user.org_id or arm.trial_id != st.trial_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="arm not found for this trial")

    monday_from = _site_local_monday(from_date)
    monday_to = _site_local_monday(to_date)

    existing = (
        await db.execute(
            select(EnrollmentWeek).where(
                EnrollmentWeek.site_id == st.site_id,
                EnrollmentWeek.trial_id == st.trial_id,
                EnrollmentWeek.arm_id == arm_id,
                EnrollmentWeek.week_start >= monday_from,
                EnrollmentWeek.week_start <= monday_to,
            )
        )
    ).scalars().all()
    by_week = {r.week_start: r for r in existing}

    # Pad missing weeks. These rows are transient — they aren't inserted until
    # the user actually saves a non-zero value.
    out: list[EnrollmentWeek | EnrollmentWeekOut] = []
    cursor = monday_from
    while cursor <= monday_to:
        if cursor in by_week:
            out.append(by_week[cursor])
        else:
            # Synthesize a virtual row. id is a sentinel UUID so the schema can
            # serialize it; the frontend distinguishes virtual rows by checking
            # whether all values are default.
            out.append(
                EnrollmentWeekOut(
                    id=UUID("00000000-0000-0000-0000-000000000000"),
                    site_id=st.site_id,
                    trial_id=st.trial_id,
                    arm_id=arm_id,
                    week_start=cursor,
                    proj_screened=0,
                    proj_randomized=0,
                    actual_screened=None,
                    actual_randomized=None,
                )
            )
        cursor += timedelta(days=7)
    return out  # type: ignore[return-value]


# --- PUT (bulk replace) -------------------------------------------------


@router.put(
    "/site-trials/{site_trial_id}/enrollment-weeks",
    response_model=list[EnrollmentWeekOut],
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def replace_enrollment_weeks(
    site_trial_id: UUID,
    payload: EnrollmentWeeksBulkIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentWeek]:
    """One save = one transaction. Past projection edits → 409. Audit rows
    written for every changed projection field; actuals are not audited."""
    st = await _ensure_site_trial(db, user, site_trial_id)
    arm = await db.get(Arm, payload.arm_id)
    if arm is None or arm.org_id != user.org_id or arm.trial_id != st.trial_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="arm not found for this trial")

    today_monday = _site_local_monday(date.today())

    # Existing rows for this (site, trial, arm) keyed by week_start.
    existing_rows = (
        await db.execute(
            select(EnrollmentWeek).where(
                EnrollmentWeek.site_id == st.site_id,
                EnrollmentWeek.trial_id == st.trial_id,
                EnrollmentWeek.arm_id == payload.arm_id,
            )
        )
    ).scalars().all()
    existing_by_week = {r.week_start: r for r in existing_rows}

    # First pass: detect past-projection edits and reject the whole save.
    offending: list[date] = []
    for spec in payload.weeks:
        wk = _site_local_monday(spec.week_start)
        if wk >= today_monday:
            continue  # not a past week
        existing = existing_by_week.get(wk)
        old_screened = existing.proj_screened if existing else 0
        old_randomized = existing.proj_randomized if existing else 0
        if (
            spec.proj_screened != old_screened
            or spec.proj_randomized != old_randomized
        ):
            offending.append(wk)

    if offending:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "past_projection_locked",
                "offending_week_starts": sorted({d.isoformat() for d in offending}),
                "detail": (
                    "Past-week projections are locked to preserve historical "
                    "plan-vs-actual variance. Edits to past weeks must be limited "
                    "to actuals."
                ),
            },
        )

    # Second pass: write the changes. Audit projection diffs (changed fields
    # only) and update or insert. Empty rows (all defaults) for weeks that
    # don't already exist are skipped — no point persisting blanks.
    out: list[EnrollmentWeek] = []
    for spec in payload.weeks:
        wk = _site_local_monday(spec.week_start)
        existing = existing_by_week.get(wk)

        is_blank = (
            spec.proj_screened == 0
            and spec.proj_randomized == 0
            and spec.actual_screened is None
            and spec.actual_randomized is None
        )
        if existing is None and is_blank:
            continue

        if existing is None:
            # Insert. No history for the initial set — that's the baseline.
            row = EnrollmentWeek(
                org_id=user.org_id,
                site_id=st.site_id,
                trial_id=st.trial_id,
                arm_id=payload.arm_id,
                week_start=wk,
                proj_screened=spec.proj_screened,
                proj_randomized=spec.proj_randomized,
                actual_screened=spec.actual_screened,
                actual_randomized=spec.actual_randomized,
            )
            db.add(row)
            await db.flush()
            existing_by_week[wk] = row
            out.append(row)
            continue

        # Update existing row. Audit changed projection fields.
        history_rows = diff_projection_fields(
            org_id=user.org_id,
            changed_by=user.id,
            existing=existing,
            new_proj_screened=spec.proj_screened,
            new_proj_randomized=spec.proj_randomized,
        )
        for h in history_rows:
            db.add(h)

        existing.proj_screened = spec.proj_screened
        existing.proj_randomized = spec.proj_randomized
        existing.actual_screened = spec.actual_screened
        existing.actual_randomized = spec.actual_randomized
        out.append(existing)

    return out


# --- GET history --------------------------------------------------------


@router.get(
    "/site-trials/{site_trial_id}/enrollment-weeks/history",
    response_model=list[EnrollmentWeekHistoryOut],
)
async def list_enrollment_history(
    site_trial_id: UUID,
    arm_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentWeekHistory]:
    st = await _ensure_site_trial(db, user, site_trial_id)
    rows = (
        await db.execute(
            select(EnrollmentWeekHistory)
            .join(
                EnrollmentWeek,
                EnrollmentWeekHistory.enrollment_week_id == EnrollmentWeek.id,
            )
            .where(
                EnrollmentWeek.site_id == st.site_id,
                EnrollmentWeek.trial_id == st.trial_id,
                EnrollmentWeek.arm_id == arm_id,
            )
            .order_by(EnrollmentWeekHistory.changed_at.desc())
        )
    ).scalars().all()
    return list(rows)


# --- GET variance -------------------------------------------------------


@router.get(
    "/trials/{trial_id}/variance",
    response_model=TrialVarianceOut,
)
async def get_trial_variance(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrialVarianceOut:
    t = await db.get(Trial, trial_id)
    if t is None or t.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    v = await compute_trial_variance(db, t)
    return TrialVarianceOut(
        randomization={
            "sum_site": v.randomization.sum_site,
            "target": v.randomization.target,
            "diff": v.randomization.diff,
        },
        screening={
            "sum_site": v.screening.sum_site,
            "target": v.screening.target,
            "diff": v.screening.diff,
        },
    )
