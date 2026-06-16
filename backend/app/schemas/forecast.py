from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class WeekRangeOut(BaseModel):
    low_count: float
    high_count: float


class ForecastCellOut(BaseModel):
    site_id: UUID
    week_start: date
    # Maps visit type ("screening" | "randomization" | "follow_up" | "other")
    # to expected count.
    visits_by_type: dict[str, float]
    visits_by_trial: dict[UUID, float]
    demand_hours: float
    capacity_hours: float
    utilization: float | None
    revenue: float
    week_range: WeekRangeOut


class DailyVisitsOut(BaseModel):
    """Per-day breakdown for one site over one month — drives the calendar
    heatmap (PRD §8.5)."""

    day: date
    visits_by_type: dict[str, float]
    demand_hours: float
    capacity_hours: float
    utilization: float | None


class MetricsRowOut(BaseModel):
    screened: int
    randomized: int
    screen_fail_rate: float | None
    screen_rate: float | None
    enrollment_rate: float | None
    pace_vs_plan: float | None
    enrollment_health_randomized: float | None
    enrollment_health_screened: float | None
    wow_screened: int | None
    wow_randomized: int | None


class TrialMetricsOut(BaseModel):
    trial_id: UUID
    trial_name: str
    randomization_target: int
    screening_target: int
    metrics: MetricsRowOut
