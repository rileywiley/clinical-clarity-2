"""Enrollment & velocity metrics (PRD §6.8).

Pure functions over aggregate weekly inputs (EnrollmentWeek lists + targets +
FPFV/LPFV). No forecast dependency — these read the same projection/actuals
data that feeds the forecast.

Limitation honored: true patient-level cycle-time metrics (screen→randomization
interval) are deferred (v1 tracks aggregate weeks, not individual patients).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from engine.types import EnrollmentWeek, MetricsRow


def _split(week: EnrollmentWeek, today_week: date) -> tuple[int, int]:
    """Apply actuals-override for past weeks (PRD §5.3)."""
    if week.week_start < today_week:
        s = week.actual_screened if week.actual_screened is not None else week.proj_screened
        r = (
            week.actual_randomized
            if week.actual_randomized is not None
            else week.proj_randomized
        )
    else:
        s, r = week.proj_screened, week.proj_randomized
    return s, r


def compute_metrics(
    weeks: Iterable[EnrollmentWeek],
    today: date,
    window_start: date,
    window_end: date,
    active_sites: int,
    randomization_goal: int,
    screening_goal: int,
) -> MetricsRow:
    """Compute one row of metrics over ``[window_start, window_end]``.

    ``active_sites`` is the number of sites whose data feeds the totals — used
    for the per-site-per-week rates. ``randomization_goal`` and
    ``screening_goal`` are the trial-level targets used for enrollment health
    ratios.

    Pass ``weeks`` as the full enrollment history (not pre-filtered to the
    window) so cumulative pace-vs-plan can be computed correctly.
    """
    weeks = sorted(weeks, key=lambda w: w.week_start)
    today_monday = today - timedelta(days=today.weekday())

    # --- Totals inside the window ------------------------------------------
    win_screened = 0
    win_randomized = 0
    week_count_in_window = 0
    for w in weeks:
        if window_start <= w.week_start <= window_end:
            s, r = _split(w, today_monday)
            win_screened += s
            win_randomized += r
            week_count_in_window += 1

    sfr = (
        (win_screened - win_randomized) / win_screened if win_screened > 0 else None
    )
    screen_rate = (
        win_screened / active_sites / week_count_in_window
        if active_sites > 0 and week_count_in_window > 0
        else None
    )
    enrollment_rate = (
        win_randomized / active_sites / week_count_in_window
        if active_sites > 0 and week_count_in_window > 0
        else None
    )

    # --- Cumulative pace vs plan (across all weeks up to today) ------------
    cum_actual_rand = 0
    cum_proj_rand = 0
    for w in weeks:
        if w.week_start < today_monday:
            cum_actual_rand += (
                w.actual_randomized
                if w.actual_randomized is not None
                else w.proj_randomized
            )
            cum_proj_rand += w.proj_randomized
    pace_vs_plan = cum_actual_rand / cum_proj_rand if cum_proj_rand > 0 else None

    # --- Enrollment health (projected total ÷ goal) ------------------------
    # "Projected" uses actuals where past, projections where future.
    total_proj_rand = 0
    total_proj_screened = 0
    for w in weeks:
        s, r = _split(w, today_monday)
        total_proj_screened += s
        total_proj_rand += r
    health_rand = (
        total_proj_rand / randomization_goal if randomization_goal > 0 else None
    )
    health_screened = (
        total_proj_screened / screening_goal if screening_goal > 0 else None
    )

    # --- Week-over-week (current vs previous within window) ----------------
    in_window = [
        (w.week_start, *_split(w, today_monday))
        for w in weeks
        if window_start <= w.week_start <= window_end
    ]
    if len(in_window) >= 2:
        _, prev_s, prev_r = in_window[-2]
        _, cur_s, cur_r = in_window[-1]
        wow_s: int | None = cur_s - prev_s
        wow_r: int | None = cur_r - prev_r
    else:
        wow_s = wow_r = None

    return MetricsRow(
        screened=win_screened,
        randomized=win_randomized,
        screen_fail_rate=sfr,
        screen_rate=screen_rate,
        enrollment_rate=enrollment_rate,
        pace_vs_plan=pace_vs_plan,
        enrollment_health_randomized=health_rand,
        enrollment_health_screened=health_screened,
        wow_screened=wow_s,
        wow_randomized=wow_r,
    )
