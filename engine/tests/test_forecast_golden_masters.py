"""Forecast golden masters (PRD §6.7).

Each test:
1. Builds a small commitment set with explicitly chosen numbers.
2. Hand-computes the expected ForecastCell values in the docstring/comments.
3. Calls compute_forecast and asserts against those expected values.

If a future change to the engine produces a different value, the test fails
loudly with the hand-computed expectation in the failure message — making the
unintended drift obvious.
"""

from __future__ import annotations

import math
from datetime import date

from engine.forecast import compute_forecast
from engine.types import VisitType
from tests._builders import attrition, commitment, site, trial, visit, week

# All fixtures anchor on a known Monday so day-arithmetic is reviewable.
MONDAY_W0 = date(2026, 6, 1)  # Mon 2026-06-01 — the "enrollment week"
MONDAY_W1 = date(2026, 6, 8)
MONDAY_W2 = date(2026, 6, 15)
TODAY = date(2026, 6, 1)
HORIZON = date(2026, 9, 30)  # ~4 months


def _cells_for_site(out: dict, site_id: str) -> dict:
    return {k[1]: v for k, v in out.items() if k[0] == site_id}


# --- 1. single_cohort_fan -------------------------------------------------


def test_single_cohort_fan() -> None:
    """
    1 site, 1 trial, 1 arm, 4 visits, no attrition.
    10 randomized in week W0. No screening visits.

    Visits (point windows, W=0 so no smearing):
      v0: randomization at day  0   → Mon W0
      v1: follow_up    at day  7   → Mon W1
      v2: follow_up    at day 14   → Mon W2
      v3: other        at day 28   → Mon W4 (out of test focus; we just check W0..W2)

    Expected counts in each week's cell:
      W0: v0 = 10
      W1: v1 = 10
      W2: v2 = 10
    Demand hours (org defaults: rand=4, follow_up=2, other=3):
      W0: 10 * 4 = 40
      W1: 10 * 2 = 20
      W2: 10 * 2 = 20
    Capacity: 2 rooms * 5 workdays * 10 hr = 100 hours/week.
    Utilization: W0 = 40/100 = 0.40; W1 = W2 = 0.20.
    """
    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 7, sort_order=1),
        visit("v2", VisitType.FOLLOW_UP, 14, sort_order=2),
        visit("v3", VisitType.OTHER, 28, sort_order=3),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(trial_=t, weeks=(week(MONDAY_W0, proj_randomized=10),))

    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    assert math.isclose(cells[MONDAY_W0].visits_by_type[VisitType.RANDOMIZATION], 10.0)
    assert math.isclose(cells[MONDAY_W1].visits_by_type[VisitType.FOLLOW_UP], 10.0)
    assert math.isclose(cells[MONDAY_W2].visits_by_type[VisitType.FOLLOW_UP], 10.0)

    assert math.isclose(cells[MONDAY_W0].demand_hours, 40.0)
    assert math.isclose(cells[MONDAY_W1].demand_hours, 20.0)
    assert math.isclose(cells[MONDAY_W2].demand_hours, 20.0)

    assert math.isclose(cells[MONDAY_W0].capacity_hours, 100.0)
    assert math.isclose(cells[MONDAY_W0].utilization, 0.40)
    assert math.isclose(cells[MONDAY_W1].utilization, 0.20)


# --- 2. multi_cohort_stacking ---------------------------------------------


def test_multi_cohort_stacking() -> None:
    """
    Two cohorts in W0 and W1, each 10 randomized, point windows.
    Visit at day 7 → cohort A's v1 lands W1, cohort B's v1 lands W2.
    Visit at day 0 → cohort A in W0, cohort B in W1.
    Visit at day 14 → cohort A in W2, cohort B in W3.

    Expected randomization-type counts per week:
      W0: 10 (cohort A v0)
      W1: 10 (cohort A v1) + 10 (cohort B v0) = 20
      W2: 10 (cohort A v2) + 10 (cohort B v1) = 20
      W3: 10 (cohort B v2)
    """
    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 7, sort_order=1),
        visit("v2", VisitType.FOLLOW_UP, 14, sort_order=2),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(
        trial_=t,
        weeks=(
            week(MONDAY_W0, proj_randomized=10),
            week(MONDAY_W1, proj_randomized=10),
        ),
    )
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    # W0: just cohort A's v0
    assert math.isclose(cells[MONDAY_W0].visits_by_trial[t.id], 10.0)
    # W1: A's v1 + B's v0
    assert math.isclose(cells[MONDAY_W1].visits_by_trial[t.id], 20.0)
    # W2: A's v2 + B's v1
    assert math.isclose(cells[MONDAY_W2].visits_by_trial[t.id], 20.0)


# --- 3. survival_decay ----------------------------------------------------


def test_survival_decay_applies_to_randomized_chain_only() -> None:
    """
    20% Standard curve, 5 visits — survival = 1.0, 0.95, 0.90, 0.85, 0.80
    over the randomized chain. Screening visits are unaffected.

    Cohort: 10 screened, 10 randomized in W0.
    Visits (all window=0):
      s : SCREENING       day -7  → anchored to W0's Mon (the first screening visit)
      v0: RANDOMIZATION   day  0  → W0
      v1: FOLLOW_UP       day  7  → W1
      v2: FOLLOW_UP       day 14  → W2
      v3: FOLLOW_UP       day 21  → W3
      v4: FOLLOW_UP       day 28  → W4

    Expected randomized-chain counts:
      v0 (i=0): 10 * 1.00 = 10.0
      v1 (i=1): 10 * 0.95 = 9.5
      v2 (i=2): 10 * 0.90 = 9.0
      v3 (i=3): 10 * 0.85 = 8.5
      v4 (i=4): 10 * 0.80 = 8.0
    Screening: 10 (unaffected).
    """
    visits = (
        visit("s", VisitType.SCREENING, -7, sort_order=0),
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=1),
        visit("v1", VisitType.FOLLOW_UP, 7, sort_order=2),
        visit("v2", VisitType.FOLLOW_UP, 14, sort_order=3),
        visit("v3", VisitType.FOLLOW_UP, 21, sort_order=4),
        visit("v4", VisitType.FOLLOW_UP, 28, sort_order=5),
    )
    t = trial(visits, curve=attrition(0.20, "Standard"))
    c = commitment(
        trial_=t,
        weeks=(week(MONDAY_W0, proj_screened=10, proj_randomized=10),),
    )
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    # Screening visit fires in W0 (anchored to Mon W0 because it's the earliest
    # screening offset, no other screening visits to relate to). 10 unaffected.
    assert math.isclose(cells[MONDAY_W0].visits_by_type[VisitType.SCREENING], 10.0)
    # Randomization in W0
    assert math.isclose(cells[MONDAY_W0].visits_by_type[VisitType.RANDOMIZATION], 10.0)
    # Follow-ups decay across weeks
    assert math.isclose(cells[MONDAY_W1].visits_by_type[VisitType.FOLLOW_UP], 9.5)
    assert math.isclose(cells[MONDAY_W2].visits_by_type[VisitType.FOLLOW_UP], 9.0)
    assert math.isclose(cells[MONDAY_W0 + (MONDAY_W2 - MONDAY_W1) * 3].visits_by_type[VisitType.FOLLOW_UP], 8.5)
    assert math.isclose(cells[MONDAY_W0 + (MONDAY_W2 - MONDAY_W1) * 4].visits_by_type[VisitType.FOLLOW_UP], 8.0)


# --- 4. window_smearing_boundary ------------------------------------------


def test_window_smearing_across_week_boundary() -> None:
    """
    1 visit with window=2 anchored ON the week boundary.
    10 patients, no attrition, visit at day 7 (Mon W1), window ±2 days.

    Triangular weights at offsets (-2,-1,0,+1,+2) = (1,2,3,2,1)/9.
    Days: Sat W0, Sun W0, Mon W1, Tue W1, Wed W1.

    Expected mass in W0: 10 * (1+2)/9 = 10 * 3/9 ≈ 3.333
    Expected mass in W1: 10 * (3+2+1)/9 = 10 * 6/9 ≈ 6.667
    Anchor week is W1 → low for W1 = 6.667, low for W0 = 0.
    high for both = expected (full smeared mass that lands there).
    """
    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=0),  # not relevant; needed for chain
        visit("v1", VisitType.FOLLOW_UP, 7, window_days=2, sort_order=1),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(trial_=t, weeks=(week(MONDAY_W0, proj_randomized=10),))
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    # v1 mass:
    w0_v1 = cells[MONDAY_W0].visits_by_type[VisitType.FOLLOW_UP]
    w1_v1 = cells[MONDAY_W1].visits_by_type[VisitType.FOLLOW_UP]
    assert math.isclose(w0_v1, 10 * 3 / 9)
    assert math.isclose(w1_v1, 10 * 6 / 9)

    # Range bounds:
    # W0 cell: anchor (Mon W1) is OUTSIDE W0 → low = 0, high = smeared in count.
    # The v0 randomization visit (10, anchored in W0) also adds 10 to both low and high.
    assert math.isclose(cells[MONDAY_W0].week_range.low_count, 10.0)
    assert math.isclose(cells[MONDAY_W0].week_range.high_count, 10.0 + 10 * 3 / 9)
    # W1 cell: anchor is INSIDE W1 → low and high both = 6.667
    assert math.isclose(cells[MONDAY_W1].week_range.low_count, 10 * 6 / 9)
    assert math.isclose(cells[MONDAY_W1].week_range.high_count, 10 * 6 / 9)


# --- 5. screened_vs_randomized --------------------------------------------


def test_screening_driven_by_screened_not_randomized() -> None:
    """
    PRD §6.2 #1: screening volume is driven directly by ``screened``, not by
    back-dating randomized patients to a screening visit.

    Cohort: 20 screened, 8 randomized in W0 (i.e. 12 screen failures).
    Visits (window=0):
      s1: SCREENING        day -28
      s2: SCREENING        day -14
      r : RANDOMIZATION    day   0

    Per PRD §6.3, screening visits all carry the full ``screened`` count.
    So s1 = 20, s2 = 20. r = 8.
    Screening anchors: s1 anchored to first operating day of W0; s2 anchored
    14 days after s1 (relative offset). Both fall outside the test cells we
    examine — what matters is the counts themselves.
    """
    visits = (
        visit("s1", VisitType.SCREENING, -28, sort_order=0),
        visit("s2", VisitType.SCREENING, -14, sort_order=1),
        visit("r", VisitType.RANDOMIZATION, 0, sort_order=2),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(
        trial_=t,
        weeks=(week(MONDAY_W0, proj_screened=20, proj_randomized=8),),
    )
    out = compute_forecast(
        [c], TODAY - (MONDAY_W0 - date(2026, 5, 4)), HORIZON
    )
    cells = _cells_for_site(out, "site-1")

    # Randomization should produce exactly 8 in W0.
    assert math.isclose(cells[MONDAY_W0].visits_by_type[VisitType.RANDOMIZATION], 8.0)
    # Each screening visit independently produces the full 20 — PRD §6.3 says
    # "Each screening visit therefore carries the full screened(w) count".
    # Total screening across all weeks = 40 (20 + 20).
    total_screening = sum(
        c.visits_by_type.get(VisitType.SCREENING, 0.0) for c in cells.values()
    )
    assert math.isclose(total_screening, 40.0)


# --- 6. hours_capacity_utilization ----------------------------------------


def test_hours_and_capacity_arithmetic() -> None:
    """
    Site: 3 rooms, 6 operating days, 8 hours/day → capacity = 144 hr/week.
    Cohort: 10 randomized, no attrition, one visit.

    Visit duration override = 1.5 hours; count in W0 = 10.
    Expected demand_hours = 10 * 1.5 = 15.
    Expected utilization = 15 / 144 ≈ 0.10417.
    """
    s = site(
        operating_weekdays=frozenset({0, 1, 2, 3, 4, 5}),
        hours_per_day=8.0,
        rooms=3,
    )
    visits = (
        visit(
            "v0",
            VisitType.RANDOMIZATION,
            0,
            duration_hours_override=1.5,
            sort_order=0,
        ),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(site_=s, trial_=t, weeks=(week(MONDAY_W0, proj_randomized=10),))
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    assert math.isclose(cells[MONDAY_W0].capacity_hours, 144.0)
    assert math.isclose(cells[MONDAY_W0].demand_hours, 15.0)
    assert math.isclose(cells[MONDAY_W0].utilization, 15.0 / 144.0)


# --- 7. revenue -----------------------------------------------------------


def test_revenue_is_count_times_price() -> None:
    """
    10 randomized, 2 visits each priced.
    v0: rand, price $500 → revenue 10 * 500 = $5000 in W0
    v1: follow_up at day 7, price $200, attrition 20% (chain of 2: 1.0, 0.8)
        → revenue 10 * 0.8 * 200 = $1600 in W1
    Unpriced visit contributes 0.
    """
    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, price=500.0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 7, price=200.0, sort_order=1),
        visit("vU", VisitType.FOLLOW_UP, 14, price=None, sort_order=2),
    )
    t = trial(visits, curve=attrition(0.20))
    c = commitment(trial_=t, weeks=(week(MONDAY_W0, proj_randomized=10),))
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    assert math.isclose(cells[MONDAY_W0].revenue, 10 * 500.0)
    # 3 randomized-chain visits → survival = (1.0, 0.5, 0.0) at indices 0,1,2.
    # Wait: D=0.20, N=3, so survival = 1 - 0.20*i/(N-1) = 1, 0.9, 0.8.
    # v1 is at index 1 → survival 0.9 → revenue = 10 * 0.9 * 200 = 1800.
    assert math.isclose(cells[MONDAY_W1].revenue, 10 * 0.9 * 200.0)


# --- 8. actuals_override --------------------------------------------------


def test_actuals_override_when_past_week_is_in_horizon() -> None:
    """Re-state actuals_override using a forecast horizon that includes the past
    week, so the cell is materialized and we can read the actual override.

    Setup: today = w0 + 2 weeks. Past week w0 has projected=10, actual=4.
    The forecast cells start at monday_of(today) by design (we don't backfill
    completed weeks). So actuals override is visible only via the *downstream*
    visits from that past cohort:

    Visits at day 0 (rand), day 14 (follow_up), day 28 (other).
    A past cohort of 4 (actual) lands:
       v0 at w0       — before today, not in output
       v1 at w0 + 14d  → this lands in w_today (today = w0+14d) → 4 expected
       v2 at w0 + 28d  → lands at w_today + 14d → 4 expected
    """
    w0 = date(2026, 6, 1)
    today = date(2026, 6, 15)  # w0 + 14 days, two weeks later

    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 14, sort_order=1),
        visit("v2", VisitType.OTHER, 28, sort_order=2),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(
        trial_=t,
        weeks=(week(w0, proj_randomized=10, actual_randomized=4),),
    )
    out = compute_forecast([c], today, HORIZON)
    cells = _cells_for_site(out, "site-1")

    # The cell for today's Monday should contain v1 from the past cohort.
    # 4 (not 10) — actuals overrode the projection.
    assert math.isclose(cells[today].visits_by_type[VisitType.FOLLOW_UP], 4.0)
    assert math.isclose(
        cells[date(2026, 6, 29)].visits_by_type[VisitType.OTHER], 4.0
    )


# --- 9. range bounds on the simple case -----------------------------------


def test_range_bounds_collapse_with_zero_window() -> None:
    """When all windows are 0, low_count == high_count == expected for every cell."""
    visits = (
        visit("v0", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 7, sort_order=1),
    )
    t = trial(visits, curve=attrition(0.0))
    c = commitment(trial_=t, weeks=(week(MONDAY_W0, proj_randomized=10),))
    out = compute_forecast([c], TODAY, HORIZON)
    cells = _cells_for_site(out, "site-1")

    for w_start, cell in cells.items():
        total = sum(cell.visits_by_type.values())
        if total > 0:
            assert math.isclose(cell.week_range.low_count, total), (
                f"week {w_start}: low {cell.week_range.low_count} != total {total}"
            )
            assert math.isclose(cell.week_range.high_count, total)
