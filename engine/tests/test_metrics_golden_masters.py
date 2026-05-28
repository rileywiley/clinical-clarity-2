"""Metrics golden masters (PRD §6.8).

Each test hand-computes the expected value and asserts. SFR, screen/enrollment
rates, pace-vs-plan, enrollment health (against both goals), week-over-week.
"""

from __future__ import annotations

import math
from datetime import date

from engine.metrics import compute_metrics
from tests._builders import week

MONDAY_W0 = date(2026, 6, 1)
MONDAY_W1 = date(2026, 6, 8)
MONDAY_W2 = date(2026, 6, 15)
MONDAY_W3 = date(2026, 6, 22)


def test_sfr_basic() -> None:
    """SFR = (screened - randomized) / screened. 100 screened, 80 randomized → 0.20."""
    weeks = (
        week(MONDAY_W0, proj_screened=50, proj_randomized=40),
        week(MONDAY_W1, proj_screened=50, proj_randomized=40),
    )
    m = compute_metrics(
        weeks,
        today=MONDAY_W0,
        window_start=MONDAY_W0,
        window_end=MONDAY_W1,
        active_sites=1,
        randomization_goal=200,
        screening_goal=250,
    )
    assert m.screened == 100
    assert m.randomized == 80
    assert math.isclose(m.screen_fail_rate, 0.20)


def test_rates_per_site_per_week() -> None:
    """4 weeks, 2 active sites, 80 screened total → 80 / 2 / 4 = 10."""
    weeks = tuple(
        week(MONDAY_W0 + (MONDAY_W1 - MONDAY_W0) * i, proj_screened=20, proj_randomized=16)
        for i in range(4)
    )
    m = compute_metrics(
        weeks,
        today=MONDAY_W0,
        window_start=MONDAY_W0,
        window_end=MONDAY_W0 + (MONDAY_W1 - MONDAY_W0) * 3,
        active_sites=2,
        randomization_goal=100,
        screening_goal=125,
    )
    assert math.isclose(m.screen_rate, 80 / 2 / 4)  # = 10
    assert math.isclose(m.enrollment_rate, 64 / 2 / 4)  # = 8


def test_pace_vs_plan_ahead_of_schedule() -> None:
    """Cum actual randomized to date 50, cum projected 40 → pace 1.25 (25% ahead)."""
    today = MONDAY_W2  # past = W0, W1; future = W2+
    weeks = (
        week(MONDAY_W0, proj_randomized=20, actual_randomized=25),
        week(MONDAY_W1, proj_randomized=20, actual_randomized=25),
        week(MONDAY_W2, proj_randomized=20),
    )
    m = compute_metrics(
        weeks,
        today=today,
        window_start=MONDAY_W0,
        window_end=MONDAY_W3,
        active_sites=1,
        randomization_goal=100,
        screening_goal=125,
    )
    assert math.isclose(m.pace_vs_plan, 50 / 40)  # 1.25


def test_enrollment_health_against_both_goals() -> None:
    """
    Total projected randomized = 80; goal = 100 → health = 0.80.
    Total projected screened = 100; goal = 125 → health = 0.80.
    """
    weeks = tuple(
        week(MONDAY_W0 + (MONDAY_W1 - MONDAY_W0) * i, proj_screened=25, proj_randomized=20)
        for i in range(4)
    )
    m = compute_metrics(
        weeks,
        today=MONDAY_W0,
        window_start=MONDAY_W0,
        window_end=MONDAY_W0 + (MONDAY_W1 - MONDAY_W0) * 3,
        active_sites=1,
        randomization_goal=100,
        screening_goal=125,
    )
    assert math.isclose(m.enrollment_health_randomized, 0.80)
    assert math.isclose(m.enrollment_health_screened, 0.80)


def test_wow_deltas_use_last_two_in_window() -> None:
    """Last two in-window weeks: 15→20 randomized → WoW = +5."""
    weeks = (
        week(MONDAY_W0, proj_screened=20, proj_randomized=15),
        week(MONDAY_W1, proj_screened=22, proj_randomized=15),
        week(MONDAY_W2, proj_screened=25, proj_randomized=20),
    )
    m = compute_metrics(
        weeks,
        today=MONDAY_W0,
        window_start=MONDAY_W0,
        window_end=MONDAY_W3,
        active_sites=1,
        randomization_goal=100,
        screening_goal=125,
    )
    assert m.wow_screened == 3  # 25 - 22
    assert m.wow_randomized == 5  # 20 - 15


def test_zero_screened_returns_none_sfr() -> None:
    """SFR undefined when screened = 0."""
    weeks = (week(MONDAY_W0, proj_screened=0, proj_randomized=0),)
    m = compute_metrics(
        weeks,
        today=MONDAY_W0,
        window_start=MONDAY_W0,
        window_end=MONDAY_W0,
        active_sites=1,
        randomization_goal=100,
        screening_goal=125,
    )
    assert m.screen_fail_rate is None
