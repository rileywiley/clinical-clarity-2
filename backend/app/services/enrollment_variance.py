"""Trial-level variance: sum of site projections vs. trial targets (PRD §7.3).

Warn-and-allow pattern: the grid uses this to render the running "87 / 100 · 13
under" hint. Never blocks the save.

Per PRD §5.3, past weeks use actuals when present; future weeks use projections.
For variance against trial targets we want the "current best estimate" — that's
the same actuals-override rule the engine uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrollment_week import EnrollmentWeek
from app.models.trial import Trial


@dataclass(frozen=True, slots=True)
class GoalVariance:
    sum_site: int
    target: int
    diff: int  # sum_site - target. Negative = under target.


@dataclass(frozen=True, slots=True)
class TrialVariance:
    randomization: GoalVariance
    screening: GoalVariance


def _site_local_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def compute_trial_variance(
    db: AsyncSession, trial: Trial, today: date | None = None
) -> TrialVariance:
    """Sum the per-week projections (or actuals where past) across every site
    assigned to this trial, then compare against the trial's targets."""
    if today is None:
        today = date.today()
    today_monday = _site_local_monday(today)

    rows = (
        await db.execute(
            select(EnrollmentWeek).where(EnrollmentWeek.trial_id == trial.id)
        )
    ).scalars().all()

    sum_screened = 0
    sum_randomized = 0
    for r in rows:
        if r.week_start < today_monday:
            s = r.actual_screened if r.actual_screened is not None else r.proj_screened
            rd = (
                r.actual_randomized
                if r.actual_randomized is not None
                else r.proj_randomized
            )
        else:
            s = r.proj_screened
            rd = r.proj_randomized
        sum_screened += s
        sum_randomized += rd

    return TrialVariance(
        randomization=GoalVariance(
            sum_site=sum_randomized,
            target=trial.enrollment_target,
            diff=sum_randomized - trial.enrollment_target,
        ),
        screening=GoalVariance(
            sum_site=sum_screened,
            target=trial.screening_target,
            diff=sum_screened - trial.screening_target,
        ),
    )
