"""Forecast computation (PRD §6.4 / §6.5).

The algorithm:

1. For each Commitment (= site × trial × arm × enrollment_weeks):
   - Compute survival per visit (screening = 1.0; randomized chain = linear back-loaded).
   - For each enrollment week:
       - For each visit:
         * Screening visit: base = screened(w), survival = 1.0,
           anchor = first-operating-day-of-enrollment-week + relative_screening_offset(v).
         * Randomized visit: base = randomized(w), survival = survival[v.id],
           anchor = randomization_day(w) + v.target_day_offset.
       - Smear ``base * survival`` across the visit's triangular window into
         per-(site, day) totals. Track each placement's anchor week for the
         range bounds computation.
2. Aggregate daily counts to (site, site-local week) cells:
   - visits_by_type, visits_by_trial
   - demand_hours via effective_duration
   - capacity_hours = rooms × operating_days_in_week × hours_per_day
   - utilization = demand_hours / capacity_hours (None if capacity == 0)
   - revenue = Σ count × visit.price (unpriced visits contribute 0)
   - week_range (low/high): see range bounds policy below

**Randomization day (PRD §6.2 #5):** v1 tracks cohorts at weekly grain. The
randomization day for a cohort enrolling in week W is taken as W's first
operating day. This is what's testable from aggregate weekly inputs.

**Screening anchor (PRD §6.3):** the first screening visit (the one with the
most-negative ``target_day_offset``) is anchored to W's first operating day.
Subsequent screening visits are placed relative to it by the difference in
day offsets (so a visit at -28 and another at -14 → the -14 visit happens 14
days *after* the -28 visit).

**Range bounds policy:** a placement whose anchor day falls inside the cell's
week contributes its full smeared count to both ``low`` and ``high``. A
placement whose anchor falls *outside* the week but whose window reaches in
contributes 0 to ``low`` (the visit might land entirely outside) and its
smeared in-week share to ``high`` (it might land entirely in). This makes
``low ≤ expected ≤ high`` an invariant, with the spread reflecting genuine
window-uncertainty between adjacent weeks.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from engine.attrition import survival_by_visit
from engine.duration import effective_duration
from engine.types import (
    Commitment,
    EnrollmentWeek,
    ForecastCell,
    Site,
    Visit,
    VisitType,
    WeekRange,
)
from engine.windows import triangular_weights


def _site_local_week_start(d: date) -> date:
    """Monday of the week containing ``d`` (weekday(): Mon=0..Sun=6)."""
    return d - timedelta(days=d.weekday())


def _first_operating_day_in_week(
    week_monday: date, operating_weekdays: frozenset[int]
) -> date:
    """Earliest operating day in the Monday-anchored week."""
    if not operating_weekdays:
        # Degenerate site with no operating days — anchor on Monday so downstream
        # math is still well-defined.
        return week_monday
    return week_monday + timedelta(days=min(operating_weekdays))


def _effective(week: EnrollmentWeek, today: date) -> tuple[float, float]:
    """PRD §5.3 / §6.2 #5 actuals override.

    For past weeks (week_start < monday_of(today)) with actuals entered, use
    actuals; otherwise use projections.
    """
    today_week = _site_local_week_start(today)
    if week.week_start < today_week:
        screened = (
            week.actual_screened if week.actual_screened is not None else week.proj_screened
        )
        randomized = (
            week.actual_randomized
            if week.actual_randomized is not None
            else week.proj_randomized
        )
    else:
        screened = week.proj_screened
        randomized = week.proj_randomized
    return float(screened), float(randomized)


def _earliest_screening_offset(visits: Iterable[Visit]) -> int:
    screen_offsets = [
        v.target_day_offset for v in visits if v.visit_type is VisitType.SCREENING
    ]
    return min(screen_offsets) if screen_offsets else 0


def _screening_anchor(
    enrollment_week_start: date,
    site_operating: frozenset[int],
    visit: Visit,
    earliest_screening_offset: int,
) -> date:
    first_day = _first_operating_day_in_week(enrollment_week_start, site_operating)
    return first_day + timedelta(days=visit.target_day_offset - earliest_screening_offset)


def _randomization_anchor(
    enrollment_week_start: date,
    site_operating: frozenset[int],
    visit: Visit,
) -> date:
    rand_day = _first_operating_day_in_week(enrollment_week_start, site_operating)
    return rand_day + timedelta(days=visit.target_day_offset)


def compute_forecast(
    commitments: Iterable[Commitment],
    today: date,
    horizon_end: date,
) -> dict[tuple[str, date], ForecastCell]:
    """Run the forecast. Returns one ``ForecastCell`` per (site_id, site-local
    week_start) within ``[monday_of(today), horizon_end]``.

    Empty weeks (no expected mass and no capacity) are omitted; weeks with
    nonzero capacity are always materialized so the UI grid shows the site.
    """
    commitments = list(commitments)
    if not commitments:
        return {}

    # Per-site totals at the day grain.
    #   daily_total[site_id][day][visit_id] = smeared count placed on that day
    daily_total: dict[str, dict[date, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    # Per-site placements indexed by anchor week, used to split low/high:
    #   anchored[site_id][anchor_week_monday][day][visit_id] = smeared count
    anchored: dict[str, dict[date, dict[date, dict[str, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    )

    visit_catalog: dict[str, Visit] = {}
    trial_by_visit: dict[str, str] = {}
    sites: dict[str, Site] = {}
    commitments_by_site: dict[str, list[Commitment]] = defaultdict(list)

    for c in commitments:
        sites[c.site.id] = c.site
        commitments_by_site[c.site.id].append(c)
        survival = survival_by_visit(c.arm.visits, c.trial.attrition)
        earliest_screen_off = _earliest_screening_offset(c.arm.visits)

        for w in c.enrollment_weeks:
            screened, randomized = _effective(w, today)
            for v in c.arm.visits:
                visit_catalog[v.id] = v
                trial_by_visit[v.id] = c.trial.id

                if v.visit_type is VisitType.SCREENING:
                    base = screened
                    surv = 1.0
                    anchor = _screening_anchor(
                        w.week_start, c.site.operating_weekdays, v, earliest_screen_off
                    )
                else:
                    base = randomized
                    surv = survival[v.id]
                    anchor = _randomization_anchor(
                        w.week_start, c.site.operating_weekdays, v
                    )

                count = base * surv
                if count == 0.0:
                    continue

                anchor_week = _site_local_week_start(anchor)
                for day, weight in triangular_weights(anchor, v.window_days).items():
                    share = count * weight
                    daily_total[c.site.id][day][v.id] += share
                    anchored[c.site.id][anchor_week][day][v.id] += share

    horizon_monday_start = _site_local_week_start(today)
    horizon_monday_end = _site_local_week_start(horizon_end)

    out: dict[tuple[str, date], ForecastCell] = {}

    for site_id, site in sites.items():
        # Capacity is independent of the week — it's a property of the site
        # (rooms × operating_days × hours_per_day).
        ops_days = len(site.operating_weekdays)
        capacity_hours_per_week = site.rooms * ops_days * site.hours_per_day

        # Use the first commitment's org defaults for the site. By construction
        # all commitments for a site share the same org context.
        org_defaults = commitments_by_site[site_id][0].org_duration_defaults
        # Build a flat list of overrides across all commitments for this site.
        all_overrides = tuple(
            o for c in commitments_by_site[site_id] for o in c.visit_overrides
        )

        week_monday = horizon_monday_start
        while week_monday <= horizon_monday_end:
            week_end = week_monday + timedelta(days=6)

            # Expected (smeared) counts per visit for this week.
            cell_visits: dict[str, float] = defaultdict(float)
            # Anchored-in-this-week portion (the part that goes into `low`).
            cell_anchored_in_week: dict[str, float] = defaultdict(float)

            site_days = daily_total.get(site_id, {})
            for day, day_visits in site_days.items():
                if week_monday <= day <= week_end:
                    for vid, count in day_visits.items():
                        cell_visits[vid] += count

            anchored_this_week = anchored.get(site_id, {}).get(week_monday, {})
            for day, day_visits in anchored_this_week.items():
                if week_monday <= day <= week_end:
                    for vid, count in day_visits.items():
                        cell_anchored_in_week[vid] += count

            has_demand = bool(cell_visits)
            has_capacity = capacity_hours_per_week > 0
            if not has_demand and not has_capacity:
                week_monday += timedelta(days=7)
                continue

            visits_by_type: dict[VisitType, float] = defaultdict(float)
            visits_by_trial: dict[str, float] = defaultdict(float)
            demand_hours = 0.0
            revenue = 0.0

            for vid, count in cell_visits.items():
                v = visit_catalog[vid]
                dur = effective_duration(v, org_defaults, all_overrides)
                visits_by_type[v.visit_type] += count
                visits_by_trial[trial_by_visit[vid]] += count
                demand_hours += count * dur
                if v.price is not None:
                    revenue += count * v.price

            utilization = (
                demand_hours / capacity_hours_per_week if has_capacity else None
            )

            expected_total = sum(cell_visits.values())
            low_total = sum(cell_anchored_in_week.values())

            out[(site_id, week_monday)] = ForecastCell(
                site_id=site_id,
                week_start=week_monday,
                visits_by_type=dict(visits_by_type),
                visits_by_trial=dict(visits_by_trial),
                demand_hours=demand_hours,
                capacity_hours=capacity_hours_per_week,
                utilization=utilization,
                revenue=revenue,
                week_range=WeekRange(low_count=low_total, high_count=expected_total),
            )
            week_monday += timedelta(days=7)

    return out
