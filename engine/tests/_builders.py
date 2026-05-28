"""Tiny builders so fixture definitions stay readable.

Not fixtures in the pytest sense — just dataclass constructors with sensible
defaults so each test only spells out what's actually relevant to it.
"""

from __future__ import annotations

from datetime import date

from engine.types import (
    Arm,
    AttritionCurve,
    Commitment,
    EnrollmentWeek,
    OrgDurationDefaults,
    Site,
    SiteTrialVisitOverride,
    Trial,
    Visit,
    VisitType,
)

WORKWEEK = frozenset({0, 1, 2, 3, 4})  # Mon–Fri


def site(
    id: str = "site-1",
    operating_weekdays: frozenset[int] = WORKWEEK,
    hours_per_day: float = 10.0,
    rooms: int = 2,
    timezone: str = "America/New_York",
) -> Site:
    return Site(
        id=id,
        timezone=timezone,
        operating_weekdays=operating_weekdays,
        hours_per_day=hours_per_day,
        rooms=rooms,
    )


def visit(
    id: str,
    visit_type: VisitType,
    target_day_offset: int,
    window_days: int = 0,
    sort_order: int = 0,
    duration_hours_override: float | None = None,
    price: float | None = None,
    arm_id: str = "arm-1",
    name: str | None = None,
) -> Visit:
    return Visit(
        id=id,
        arm_id=arm_id,
        name=name or id,
        visit_type=visit_type,
        target_day_offset=target_day_offset,
        window_days=window_days,
        sort_order=sort_order,
        duration_hours_override=duration_hours_override,
        price=price,
    )


def attrition(total: float = 0.0, name: str = "Test") -> AttritionCurve:
    return AttritionCurve(id=f"curve-{name}", name=name, total_dropout_pct=total)


def trial(
    visits: tuple[Visit, ...],
    *,
    id: str = "trial-1",
    name: str = "Test Trial",
    fpfv: date = date(2026, 1, 5),
    lpfv: date = date(2027, 1, 4),
    lplv: date = date(2028, 1, 3),
    curve: AttritionCurve | None = None,
) -> Trial:
    arm = Arm(id="arm-1", trial_id=id, name="Default Arm", visits=visits)
    return Trial(
        id=id,
        name=name,
        fpfv=fpfv,
        lpfv=lpfv,
        lplv=lplv,
        arms=(arm,),
        attrition=curve or attrition(0.0),
    )


def week(
    week_start: date,
    proj_screened: int = 0,
    proj_randomized: int = 0,
    actual_screened: int | None = None,
    actual_randomized: int | None = None,
) -> EnrollmentWeek:
    return EnrollmentWeek(
        week_start=week_start,
        proj_screened=proj_screened,
        proj_randomized=proj_randomized,
        actual_screened=actual_screened,
        actual_randomized=actual_randomized,
    )


def commitment(
    *,
    site_: Site | None = None,
    trial_: Trial,
    weeks: tuple[EnrollmentWeek, ...],
    overrides: tuple[SiteTrialVisitOverride, ...] = (),
    defaults: OrgDurationDefaults | None = None,
) -> Commitment:
    return Commitment(
        site=site_ or site(),
        trial=trial_,
        arm=trial_.arms[0],
        enrollment_weeks=weeks,
        visit_overrides=overrides,
        org_duration_defaults=defaults
        or OrgDurationDefaults(screening=5.0, randomization=4.0, follow_up=2.0, other=3.0),
    )
