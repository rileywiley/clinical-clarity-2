"""DB → engine bridge for forecasts (PRD §6, §9.2 Phase 4).

The engine (``/engine``) is pure Python with zero web/DB imports — CLAUDE.md
golden rule #2. This module is the *only* place that touches both worlds. It:

  1. Reads Site / Trial / Arm / Visit / AttritionCurve / EnrollmentWeek /
     OrgSettings / SiteTrialVisitOverride from Postgres.
  2. Constructs the engine's input dataclasses (``engine.types.Commitment``).
  3. Calls ``engine.forecast.compute_forecast``.
  4. Returns the engine's output unchanged.

Any future feature that wants forecasts goes through here. The engine itself
never grows a DB import; if it ever does, ``engine/tests/test_engine_purity.py``
will fail loud.
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Iterable
from datetime import date
from uuid import UUID

from engine.forecast import compute_forecast
from engine.types import (
    Arm,
    AttritionCurve,
    Commitment,
    EnrollmentWeek,
    ForecastCell,
    OrgDurationDefaults,
    Site,
    SiteTrialVisitOverride,
    Trial,
    Visit,
    VisitType,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attrition_curve import AttritionCurve as DbAttritionCurve
from app.models.enrollment_week import EnrollmentWeek as DbEnrollmentWeek
from app.models.org_settings import OrgSettings
from app.models.site import Site as DbSite
from app.models.site_trial import SiteTrial
from app.models.site_trial import SiteTrialVisitOverride as DbStvo
from app.models.trial import Arm as DbArm
from app.models.trial import Trial as DbTrial
from app.models.trial import TrialStatus
from app.models.visit import Visit as DbVisit


class ForecastScope(enum.StrEnum):
    """Which trial statuses a forecast or report includes (PRD §6.9).

    The engine is status-agnostic; scope selection happens here in the adapter
    so the network forecast, per-site views, metrics, and exports can all split
    committed (active) volume from future pipeline (planned) volume.
    """

    ACTIVE = "active"  # committed, currently-running trials only (default)
    PLANNED = "planned"  # future pipeline only
    COMBINED = "combined"  # active + planned together


_SCOPE_STATUSES: dict[ForecastScope, tuple[TrialStatus, ...]] = {
    ForecastScope.ACTIVE: (TrialStatus.ACTIVE,),
    ForecastScope.PLANNED: (TrialStatus.PLANNED,),
    ForecastScope.COMBINED: (TrialStatus.ACTIVE, TrialStatus.PLANNED),
}


def scope_statuses(scope: ForecastScope) -> tuple[TrialStatus, ...]:
    """Map a ForecastScope to the trial statuses it selects. ``draft`` and
    ``archived`` are never forecast under any scope."""
    return _SCOPE_STATUSES[scope]


def _to_engine_visit(v: DbVisit) -> Visit:
    return Visit(
        id=str(v.id),
        arm_id=str(v.arm_id),
        name=v.name,
        visit_type=VisitType(v.visit_type.value),
        target_day_offset=v.target_day_offset,
        window_days=v.window_days,
        sort_order=v.sort_order,
        duration_hours_override=(
            float(v.duration_hours_override)
            if v.duration_hours_override is not None
            else None
        ),
        price=float(v.price) if v.price is not None else None,
        cost=float(v.cost) if v.cost is not None else None,
    )


def _to_engine_attrition(c: DbAttritionCurve) -> AttritionCurve:
    return AttritionCurve(
        id=str(c.id),
        name=c.name,
        total_dropout_pct=float(c.total_dropout_pct),
    )


def _to_engine_site(s: DbSite) -> Site:
    return Site(
        id=str(s.id),
        timezone=s.timezone,
        operating_weekdays=frozenset(s.operating_weekdays),
        hours_per_day=float(s.hours_per_day),
        rooms=s.rooms,
    )


def _to_engine_week(w: DbEnrollmentWeek) -> EnrollmentWeek:
    return EnrollmentWeek(
        week_start=w.week_start,
        proj_screened=w.proj_screened,
        proj_randomized=w.proj_randomized,
        actual_screened=w.actual_screened,
        actual_randomized=w.actual_randomized,
    )


def _org_duration_defaults_from(settings: OrgSettings) -> OrgDurationDefaults:
    return OrgDurationDefaults(
        screening=float(settings.dur_screening_hours),
        randomization=float(settings.dur_randomization_hours),
        follow_up=float(settings.dur_follow_up_hours),
        other=float(settings.dur_other_hours),
    )


async def build_commitments(
    db: AsyncSession,
    org_id: UUID,
    *,
    trial_ids: Iterable[UUID] | None = None,
    site_ids: Iterable[UUID] | None = None,
    statuses: Collection[TrialStatus] | None = (TrialStatus.ACTIVE,),
) -> list[Commitment]:
    """Construct ``Commitment`` tuples from persisted data.

    Filters:
      - ``trial_ids`` — only build commitments for these trials. Default: all.
      - ``site_ids`` — only build commitments for these sites. Default: all.
      - ``statuses`` — restrict to trials in these statuses. Default: active
        only (preserves the original behavior). Pass a wider set (e.g. via
        ``scope_statuses(ForecastScope.COMBINED)``) to include planned trials,
        or ``None`` to skip status filtering entirely — used by single-trial
        detail views that should preview a trial regardless of its status.

    Inactive sites and inactive SiteTrial assignments are *always* excluded —
    we never forecast against disabled sites/assignments, under any scope.

    The DB calls are kept linear rather than joined, in part for clarity and
    in part because RLS is policy-per-table and a single big JOIN is no
    cheaper than the small per-entity reads at v1 scale.
    """
    # --- OrgSettings (one row per org) -----------------------------------
    settings = (
        await db.execute(select(OrgSettings).where(OrgSettings.org_id == org_id))
    ).scalar_one()
    org_defaults = _org_duration_defaults_from(settings)

    # --- Sites ------------------------------------------------------------
    # Disabled sites are never forecast, regardless of scope.
    sites_q = select(DbSite).where(DbSite.org_id == org_id, DbSite.active.is_(True))
    if site_ids is not None:
        site_ids_list = list(site_ids)
        if not site_ids_list:
            return []
        sites_q = sites_q.where(DbSite.id.in_(site_ids_list))
    sites = (await db.execute(sites_q)).scalars().all()
    sites_by_id: dict[UUID, DbSite] = {s.id: s for s in sites}
    if not sites_by_id:
        return []

    # --- Trials -----------------------------------------------------------
    trials_q = select(DbTrial).where(DbTrial.org_id == org_id)
    if statuses is not None:
        trials_q = trials_q.where(DbTrial.status.in_(tuple(statuses)))
    if trial_ids is not None:
        trial_ids_list = list(trial_ids)
        if not trial_ids_list:
            return []
        trials_q = trials_q.where(DbTrial.id.in_(trial_ids_list))
    trials = (await db.execute(trials_q)).scalars().all()
    trials_by_id: dict[UUID, DbTrial] = {t.id: t for t in trials}
    if not trials_by_id:
        return []

    # --- AttritionCurves (only the ones referenced by these trials) ------
    curve_ids = {t.attrition_curve_id for t in trials if t.attrition_curve_id}
    curves_by_id: dict[UUID, DbAttritionCurve] = {}
    if curve_ids:
        curves = (
            await db.execute(
                select(DbAttritionCurve).where(DbAttritionCurve.id.in_(curve_ids))
            )
        ).scalars().all()
        curves_by_id = {c.id: c for c in curves}

    # --- Arms + Visits ----------------------------------------------------
    arms = (
        await db.execute(
            select(DbArm).where(DbArm.trial_id.in_(trials_by_id.keys()))
        )
    ).scalars().all()
    arms_by_id: dict[UUID, DbArm] = {a.id: a for a in arms}

    visits = (
        await db.execute(
            select(DbVisit)
            .where(DbVisit.arm_id.in_(arms_by_id.keys()))
            .order_by(DbVisit.sort_order, DbVisit.target_day_offset)
        )
    ).scalars().all()
    visits_by_arm: dict[UUID, list[DbVisit]] = {}
    for v in visits:
        visits_by_arm.setdefault(v.arm_id, []).append(v)

    # --- SiteTrials (assignments) ----------------------------------------
    # Disabled assignments are never forecast, regardless of scope.
    st_q = select(SiteTrial).where(
        SiteTrial.trial_id.in_(trials_by_id.keys()),
        SiteTrial.site_id.in_(sites_by_id.keys()),
        SiteTrial.active.is_(True),
    )
    site_trials = (await db.execute(st_q)).scalars().all()
    if not site_trials:
        return []

    # --- SiteTrialVisitOverrides (sparse) --------------------------------
    stvo_rows = (
        await db.execute(
            select(DbStvo).where(DbStvo.site_trial_id.in_([st.id for st in site_trials]))
        )
    ).scalars().all()
    stvo_by_site_trial: dict[UUID, list[DbStvo]] = {}
    for o in stvo_rows:
        stvo_by_site_trial.setdefault(o.site_trial_id, []).append(o)

    # --- EnrollmentWeeks per (site, trial, arm) -------------------------
    # We fetch all weeks for every (site, trial) pair in one query, then
    # bucket in Python.
    ew_rows = (
        await db.execute(
            select(DbEnrollmentWeek).where(
                DbEnrollmentWeek.trial_id.in_(trials_by_id.keys()),
                DbEnrollmentWeek.site_id.in_(sites_by_id.keys()),
            )
        )
    ).scalars().all()
    ew_by_key: dict[tuple[UUID, UUID, UUID], list[DbEnrollmentWeek]] = {}
    for w in ew_rows:
        ew_by_key.setdefault((w.site_id, w.trial_id, w.arm_id), []).append(w)

    # --- Assemble commitments --------------------------------------------
    commitments: list[Commitment] = []
    for st in site_trials:
        trial = trials_by_id[st.trial_id]
        if trial.attrition_curve_id is None:
            # No curve assigned — engine requires one. Skip silently; the
            # trial activation gate (Phase 2) should have caught this before
            # any forecast call. Callers that want to render drafts can pass
            # statuses=None but should expect missing forecasts.
            continue
        curve_db = curves_by_id.get(trial.attrition_curve_id)
        if curve_db is None:
            continue
        curve = _to_engine_attrition(curve_db)

        for arm_db in (a for a in arms_by_id.values() if a.trial_id == trial.id):
            visits_db = visits_by_arm.get(arm_db.id, [])
            if not visits_db:
                continue
            arm = Arm(
                id=str(arm_db.id),
                trial_id=str(trial.id),
                name=arm_db.name,
                visits=tuple(_to_engine_visit(v) for v in visits_db),
            )
            engine_trial = Trial(
                id=str(trial.id),
                name=trial.name,
                fpfv=trial.fpfv,
                lpfv=trial.lpfv,
                lplv=trial.lplv,
                arms=(arm,),  # one arm per commitment — engine handles multi-arm via multiple commitments
                attrition=curve,
            )
            weeks_db = ew_by_key.get((st.site_id, trial.id, arm_db.id), [])
            overrides_db = stvo_by_site_trial.get(st.id, [])
            commitments.append(
                Commitment(
                    site=_to_engine_site(sites_by_id[st.site_id]),
                    trial=engine_trial,
                    arm=arm,
                    enrollment_weeks=tuple(_to_engine_week(w) for w in weeks_db),
                    visit_overrides=tuple(
                        SiteTrialVisitOverride(
                            visit_id=str(o.visit_id),
                            duration_hours=float(o.duration_hours),
                        )
                        for o in overrides_db
                    ),
                    org_duration_defaults=org_defaults,
                )
            )

    return commitments


async def compute_network_forecast(
    db: AsyncSession,
    org_id: UUID,
    *,
    today: date,
    horizon_end: date,
    trial_ids: Iterable[UUID] | None = None,
    site_ids: Iterable[UUID] | None = None,
    scope: ForecastScope = ForecastScope.ACTIVE,
    any_status: bool = False,
) -> dict[tuple[str, date], ForecastCell]:
    """Build commitments + run the engine. Returns the engine's output keyed
    by ``(site_id_str, week_start)``.

    ``scope`` selects which trial statuses contribute (PRD §6.9); it defaults to
    active-only. Set ``any_status=True`` to skip status filtering entirely —
    used by single-trial detail views that preview a trial regardless of its
    status (draft/planned/active/archived).
    """
    effective_statuses = None if any_status else scope_statuses(scope)
    commitments = await build_commitments(
        db, org_id, trial_ids=trial_ids, site_ids=site_ids, statuses=effective_statuses
    )
    if not commitments:
        return {}
    return compute_forecast(commitments, today, horizon_end)
