"""Forecast + metrics endpoints (PRD §8.1–8.5).

Sits on top of `services/forecast_adapter.py` and `services/metrics_adapter.py`.
All endpoints are RLS-scoped via the standard `get_db` dependency.

Date conventions:
- ``from`` / ``to`` are inclusive site-local Mondays. Server snaps to the
  Monday of the given date if it's mid-week.
- ``today`` is server-side date.today(). Frontends never pass it.
- Calendar endpoint takes a ``month`` (YYYY-MM) and returns one full month's
  daily cells.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from uuid import UUID

from engine.forecast import compute_daily_forecast
from engine.types import ForecastCell, MetricsRow
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.site import Site
from app.models.trial import Trial
from app.models.user import User
from app.schemas.forecast import (
    DailyVisitsOut,
    ForecastCellOut,
    MetricsRowOut,
    TrialMetricsOut,
    WeekRangeOut,
)
from app.services.forecast_adapter import (
    ForecastScope,
    build_commitments,
    compute_network_forecast,
    scope_statuses,
)
from app.services.metrics_adapter import (
    compute_site_metrics_per_trial,
    compute_trial_metrics,
)

router = APIRouter(tags=["forecast"])

# Shared query param: which trial statuses a report includes (PRD §6.9).
# Defaults to active-only so existing callers keep today's behavior.
ScopeParam = Query(
    default=ForecastScope.ACTIVE,
    description="Trial-status scope: active (default), planned, or combined.",
)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _parse_month(month: str) -> tuple[date, date]:
    """Parse 'YYYY-MM' → (first_day, last_day)."""
    try:
        year, mo = month.split("-")
        y, m = int(year), int(mo)
        if not (1 <= m <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must be YYYY-MM"
        ) from None
    first = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    return first, last


def _cell_to_out(c: ForecastCell) -> ForecastCellOut:
    return ForecastCellOut(
        site_id=UUID(c.site_id),
        week_start=c.week_start,
        visits_by_type={vt.value: count for vt, count in c.visits_by_type.items()},
        visits_by_trial={UUID(tid): count for tid, count in c.visits_by_trial.items()},
        demand_hours=c.demand_hours,
        capacity_hours=c.capacity_hours,
        utilization=c.utilization,
        revenue=c.revenue,
        week_range=WeekRangeOut(
            low_count=c.week_range.low_count, high_count=c.week_range.high_count
        ),
    )


def _metrics_to_out(m: MetricsRow) -> MetricsRowOut:
    return MetricsRowOut(
        screened=m.screened,
        randomized=m.randomized,
        screen_fail_rate=m.screen_fail_rate,
        screen_rate=m.screen_rate,
        enrollment_rate=m.enrollment_rate,
        pace_vs_plan=m.pace_vs_plan,
        enrollment_health_randomized=m.enrollment_health_randomized,
        enrollment_health_screened=m.enrollment_health_screened,
        wow_screened=m.wow_screened,
        wow_randomized=m.wow_randomized,
    )


# --- Network grid (PRD §8.1) --------------------------------------------


@router.get("/forecast/network", response_model=list[ForecastCellOut])
async def network_forecast(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    scope: ForecastScope = ScopeParam,
) -> list[ForecastCellOut]:
    today = date.today()
    f = _monday(from_date if from_date else today)
    # Default horizon: 12 weeks visible (matches PRD §8.1 default).
    t = to_date if to_date else f + timedelta(weeks=12)
    cells = await compute_network_forecast(
        db, user.org_id, today=today, horizon_end=t, scope=scope
    )
    # Filter to cells inside [f, t] — compute_forecast may emit one Monday
    # before today (today's Monday) which we want included; nothing earlier.
    return [
        _cell_to_out(c) for c in cells.values() if f <= c.week_start <= t
    ]


# --- Per-site forecast (PRD §8.2) ---------------------------------------


@router.get(
    "/sites/{site_id}/forecast",
    response_model=list[ForecastCellOut],
)
async def site_forecast(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    scope: ForecastScope = ScopeParam,
) -> list[ForecastCellOut]:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    today = date.today()
    f = _monday(from_date if from_date else today)
    t = to_date if to_date else f + timedelta(weeks=18)  # longer for chart
    cells = await compute_network_forecast(
        db, user.org_id, today=today, horizon_end=t, site_ids=[site_id], scope=scope
    )
    return [
        _cell_to_out(c)
        for (sid, _wk), c in cells.items()
        if sid == str(site_id) and f <= c.week_start <= t
    ]


# --- Per-site calendar (PRD §8.5) ---------------------------------------


@router.get(
    "/sites/{site_id}/forecast/calendar",
    response_model=list[DailyVisitsOut],
)
async def site_calendar(
    site_id: UUID,
    month: str = Query(..., description="YYYY-MM"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    scope: ForecastScope = ScopeParam,
) -> list[DailyVisitsOut]:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    first, last = _parse_month(month)
    commitments = await build_commitments(
        db, user.org_id, site_ids=[site_id], statuses=scope_statuses(scope)
    )
    daily = compute_daily_forecast(commitments, str(site_id), first, last)
    return [
        DailyVisitsOut(
            day=cell.day,
            visits_by_type={vt.value: count for vt, count in cell.visits_by_type.items()},
            demand_hours=cell.demand_hours,
            capacity_hours=cell.capacity_hours,
            utilization=cell.utilization,
        )
        for cell in sorted(daily.values(), key=lambda c: c.day)
    ]


# --- Per-trial forecast (PRD §8.3) --------------------------------------


@router.get(
    "/trials/{trial_id}/forecast",
    response_model=list[ForecastCellOut],
)
async def trial_forecast(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> list[ForecastCellOut]:
    trial = await db.get(Trial, trial_id)
    if trial is None or trial.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    today = date.today()
    f = _monday(from_date if from_date else today)
    t = to_date if to_date else f + timedelta(weeks=18)
    # A trial-detail forecast previews this specific trial regardless of its
    # status (draft/planned/active/archived) — scope filtering doesn't apply.
    cells = await compute_network_forecast(
        db, user.org_id, today=today, horizon_end=t, trial_ids=[trial_id], any_status=True
    )
    return [
        _cell_to_out(c) for c in cells.values() if f <= c.week_start <= t
    ]


# --- Per-trial metrics (PRD §6.8, §8.4) --------------------------------


@router.get(
    "/trials/{trial_id}/metrics",
    response_model=TrialMetricsOut,
)
async def trial_metrics(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    window_start: date | None = Query(default=None),
    window_end: date | None = Query(default=None),
    site_id: UUID | None = Query(default=None),
) -> TrialMetricsOut:
    trial = await db.get(Trial, trial_id)
    if trial is None or trial.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    today = date.today()
    ws = window_start or _monday(today - timedelta(weeks=12))
    we = window_end or _monday(today)
    m = await compute_trial_metrics(
        db,
        trial,
        window_start=ws,
        window_end=we,
        today=today,
        site_id=site_id,
    )
    return TrialMetricsOut(
        trial_id=trial.id,
        trial_name=trial.name,
        randomization_target=trial.enrollment_target,
        screening_target=trial.screening_target,
        metrics=_metrics_to_out(m),
    )


# --- Per-site metrics across trials (PRD §8.4) -------------------------


@router.get(
    "/sites/{site_id}/metrics",
    response_model=list[TrialMetricsOut],
)
async def site_metrics(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    window_start: date | None = Query(default=None),
    window_end: date | None = Query(default=None),
    scope: ForecastScope = ScopeParam,
) -> list[TrialMetricsOut]:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    today = date.today()
    ws = window_start or _monday(today - timedelta(weeks=12))
    we = window_end or _monday(today)
    rows = await compute_site_metrics_per_trial(
        db,
        site_id,
        user.org_id,
        window_start=ws,
        window_end=we,
        today=today,
        statuses=scope_statuses(scope),
    )
    return [
        TrialMetricsOut(
            trial_id=t.id,
            trial_name=t.name,
            randomization_target=t.enrollment_target,
            screening_target=t.screening_target,
            metrics=_metrics_to_out(m),
        )
        for t, m in rows
    ]


# --- Network-wide trial list (helper for legends) ---------------------


@router.get("/active-trials", response_model=list[dict])
async def list_active_trials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    scope: ForecastScope = ScopeParam,
) -> list[dict]:
    """Lightweight list of in-scope trials for color legend population in the
    network-level views. Returns just id + name. Honors the same ``scope`` as
    the forecast so the legend matches what's plotted (PRD §6.9); defaults to
    active so the legacy ``/active-trials`` name still reads true.

    Note: lives at ``/active-trials`` (not ``/trials/active``) because the
    trials router registers ``/trials/{trial_id}`` first, which would shadow
    any ``/trials/active`` route — FastAPI would try to parse ``"active"`` as
    a UUID and return 422.
    """
    rows = (
        await db.execute(
            select(Trial.id, Trial.name)
            .where(
                Trial.org_id == user.org_id,
                Trial.status.in_(scope_statuses(scope)),
            )
            .order_by(Trial.name)
        )
    ).all()
    return [{"id": str(r[0]), "name": r[1]} for r in rows]
