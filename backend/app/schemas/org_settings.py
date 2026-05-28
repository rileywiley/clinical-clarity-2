from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrgSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    dur_screening_hours: float
    dur_randomization_hours: float
    dur_follow_up_hours: float
    dur_other_hours: float
    util_threshold_green_max: float
    util_threshold_amber_max: float
    default_grid_weeks_visible: int
    default_horizon_months: int
    default_site_hours_per_day: float
    default_attrition_curve_id: UUID | None
    currency: str


class OrgSettingsPatch(BaseModel):
    """Every field optional — PATCH semantics. None means "don't change."""

    dur_screening_hours: float | None = Field(default=None, ge=0)
    dur_randomization_hours: float | None = Field(default=None, ge=0)
    dur_follow_up_hours: float | None = Field(default=None, ge=0)
    dur_other_hours: float | None = Field(default=None, ge=0)
    util_threshold_green_max: float | None = Field(default=None, ge=0, le=100)
    util_threshold_amber_max: float | None = Field(default=None, ge=0, le=100)
    default_grid_weeks_visible: int | None = Field(default=None, ge=1, le=104)
    default_horizon_months: int | None = Field(default=None, ge=1, le=60)
    default_site_hours_per_day: float | None = Field(default=None, ge=0)
    default_attrition_curve_id: UUID | None = None
