"""DB → engine bridge for enrollment metrics (PRD §6.8, §8.4).

Same shape as forecast_adapter.py — the engine's metrics module stays pure;
this adapter does the DB reads and hands the engine plain inputs.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from engine.metrics import compute_metrics
from engine.types import EnrollmentWeek, MetricsRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrollment_week import EnrollmentWeek as DbEnrollmentWeek
from app.models.site_trial import SiteTrial
from app.models.trial import Trial as DbTrial


def _to_engine_week(w: DbEnrollmentWeek) -> EnrollmentWeek:
    return EnrollmentWeek(
        week_start=w.week_start,
        proj_screened=w.proj_screened,
        proj_randomized=w.proj_randomized,
        actual_screened=w.actual_screened,
        actual_randomized=w.actual_randomized,
    )


async def compute_trial_metrics(
    db: AsyncSession,
    trial: DbTrial,
    *,
    window_start: date,
    window_end: date,
    today: date,
    site_id: UUID | None = None,
) -> MetricsRow:
    """One row for a trial, optionally scoped to one site."""
    ew_q = select(DbEnrollmentWeek).where(DbEnrollmentWeek.trial_id == trial.id)
    if site_id is not None:
        ew_q = ew_q.where(DbEnrollmentWeek.site_id == site_id)
    weeks = (await db.execute(ew_q)).scalars().all()

    st_q = select(SiteTrial).where(
        SiteTrial.trial_id == trial.id, SiteTrial.active.is_(True)
    )
    if site_id is not None:
        st_q = st_q.where(SiteTrial.site_id == site_id)
    active_sites = len((await db.execute(st_q)).scalars().all())

    return compute_metrics(
        (_to_engine_week(w) for w in weeks),
        today=today,
        window_start=window_start,
        window_end=window_end,
        active_sites=active_sites if site_id is None else 1,
        randomization_goal=trial.enrollment_target,
        screening_goal=trial.screening_target,
    )


async def compute_site_metrics_per_trial(
    db: AsyncSession,
    site_id: UUID,
    org_id: UUID,
    *,
    window_start: date,
    window_end: date,
    today: date,
) -> list[tuple[DbTrial, MetricsRow]]:
    """All trials assigned to the site, each with its MetricsRow.

    Caller uses this for the per-site metrics panel + the Metrics page's
    site-grouping view.
    """
    # Trials assigned to this site via active SiteTrial.
    rows = (
        await db.execute(
            select(SiteTrial, DbTrial)
            .join(DbTrial, DbTrial.id == SiteTrial.trial_id)
            .where(
                SiteTrial.site_id == site_id,
                SiteTrial.org_id == org_id,
                SiteTrial.active.is_(True),
            )
        )
    ).all()

    out: list[tuple[DbTrial, MetricsRow]] = []
    for _st, trial in rows:
        m = await compute_trial_metrics(
            db,
            trial,
            window_start=window_start,
            window_end=window_end,
            today=today,
            site_id=site_id,
        )
        out.append((trial, m))
    return out
