"""Engine inputs and outputs — plain dataclasses, zero web/DB/HTTP imports.

These types are the engine's contract. The backend (Phase 4 wiring) is responsible
for fetching from Postgres and constructing these dataclasses; the engine itself
never imports SQLAlchemy or anything web-shaped (CLAUDE.md golden rule #2).

IDs are typed as ``str`` rather than UUID so the engine can be exercised from
fixtures and the backend doesn't have to choose between exposing UUIDs to numpy
or wrapping them. Equality and dict-keying are the only operations performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class VisitType(StrEnum):
    """Visit categories per PRD §5.1. Drives which driver populates the visit
    (screening uses ``screened``; the rest use ``randomized``) and which org-level
    duration default applies."""

    SCREENING = "screening"
    RANDOMIZATION = "randomization"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Site:
    """Capacity inputs. ``operating_weekdays`` is an iterable of ints 0..6 with
    Monday=0 (Python's isoweekday-style numbering minus 1).
    """

    id: str
    timezone: str  # IANA, e.g. "America/New_York"
    operating_weekdays: frozenset[int]
    hours_per_day: float
    rooms: int


@dataclass(frozen=True, slots=True)
class AttritionCurve:
    """Per-trial attrition. v1 shape = linear back-loaded by visit index.

    See [[project-engine-modeling-decisions]] for the rationale: linear is the
    most defensible shape that's also tractable to hand-compute for fixtures.
    """

    id: str
    name: str
    total_dropout_pct: float  # 0..1 — e.g. 0.20 for Standard


@dataclass(frozen=True, slots=True)
class Visit:
    """One SoA row. ``target_day_offset`` is signed days from randomization day
    (negative for screening visits)."""

    id: str
    arm_id: str
    name: str
    visit_type: VisitType
    target_day_offset: int
    window_days: int  # ± days around the target
    sort_order: int
    duration_hours_override: float | None = None  # None = inherit org type default
    price: float | None = None  # None = revenue not yet priced
    cost: float | None = None  # structure-only in v1 (PRD §10.1)


@dataclass(frozen=True, slots=True)
class Arm:
    id: str
    trial_id: str
    name: str
    visits: tuple[Visit, ...]  # ordered by sort_order


@dataclass(frozen=True, slots=True)
class Trial:
    id: str
    name: str
    fpfv: date  # First Patient First Visit — enrollment window start
    lpfv: date  # Last Patient First Visit — enrollment window close
    lplv: date  # Last Patient Last Visit — natural forecast horizon
    arms: tuple[Arm, ...]
    attrition: AttritionCurve


@dataclass(frozen=True, slots=True)
class EnrollmentWeek:
    """One projection + actual record for a (site, trial, arm, week)."""

    week_start: date  # site-local Monday
    proj_screened: int
    proj_randomized: int
    actual_screened: int | None = None
    actual_randomized: int | None = None


@dataclass(frozen=True, slots=True)
class SiteTrialVisitOverride:
    """Per-(site, visit) duration override (PRD §5.1)."""

    visit_id: str
    duration_hours: float


@dataclass(frozen=True, slots=True)
class OrgDurationDefaults:
    """Org-level duration defaults (PRD §5.1 OrgSettings, the duration columns).

    The engine receives these as an input rather than reading OrgSettings directly —
    that resolution lives in the backend. Keeps the engine pure.
    """

    screening: float
    randomization: float
    follow_up: float
    other: float


@dataclass(frozen=True, slots=True)
class Commitment:
    """One site's full forecast input for a single trial-arm.

    A forecast run is a list of Commitments. The engine stacks them per-site to
    produce the per-(site, week) cells.
    """

    site: Site
    trial: Trial
    arm: Arm
    enrollment_weeks: tuple[EnrollmentWeek, ...]
    visit_overrides: tuple[SiteTrialVisitOverride, ...] = ()
    org_duration_defaults: OrgDurationDefaults = field(
        default_factory=lambda: OrgDurationDefaults(
            screening=5.0, randomization=4.0, follow_up=2.0, other=3.0
        )
    )


# --- Outputs ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeekRange:
    """Earliest/latest mass placement for a (site, week) cell — the low/high
    forecast range derived from window smearing (PRD §6.2 rule #4)."""

    low_count: float
    high_count: float


@dataclass(frozen=True, slots=True)
class ForecastCell:
    """One (site, week) of forecast output (PRD §6.5)."""

    site_id: str
    week_start: date  # site-local Monday
    visits_by_type: dict[VisitType, float]
    visits_by_trial: dict[str, float]
    demand_hours: float
    capacity_hours: float
    utilization: float | None  # None when capacity_hours == 0
    revenue: float
    week_range: WeekRange


@dataclass(frozen=True, slots=True)
class MetricsRow:
    """One row of PRD §6.8 enrollment/velocity metrics.

    Some fields are None when their inputs are insufficient (e.g. SFR when
    screened=0). Callers display "—" for None.
    """

    screened: int
    randomized: int
    screen_fail_rate: float | None
    screen_rate: float | None  # screened ÷ active_sites ÷ weeks
    enrollment_rate: float | None  # randomized ÷ active_sites ÷ weeks
    pace_vs_plan: float | None  # cumulative actual ÷ cumulative projected
    enrollment_health_randomized: float | None  # projected by LPFV ÷ goal
    enrollment_health_screened: float | None
    wow_screened: int | None
    wow_randomized: int | None
