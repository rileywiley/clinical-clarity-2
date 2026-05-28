from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentWeekIn(BaseModel):
    """One row in the bulk-replace payload."""

    week_start: date
    proj_screened: int = Field(default=0, ge=0)
    proj_randomized: int = Field(default=0, ge=0)
    actual_screened: int | None = Field(default=None, ge=0)
    actual_randomized: int | None = Field(default=None, ge=0)


class EnrollmentWeeksBulkIn(BaseModel):
    """Bulk save: also names the arm so a single site-trial with multiple arms
    can save them separately."""

    arm_id: UUID
    weeks: list[EnrollmentWeekIn]


class EnrollmentWeekOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    trial_id: UUID
    arm_id: UUID
    week_start: date
    proj_screened: int
    proj_randomized: int
    actual_screened: int | None
    actual_randomized: int | None


class GoalVarianceOut(BaseModel):
    sum_site: int
    target: int
    diff: int


class TrialVarianceOut(BaseModel):
    randomization: GoalVarianceOut
    screening: GoalVarianceOut


class EnrollmentWeekHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enrollment_week_id: UUID
    field: str
    old_value: int | None
    new_value: int | None
    changed_by: UUID | None
    changed_at: datetime


class PastProjectionEditError(BaseModel):
    """Returned with 409 when the user tries to edit a past projection cell."""

    error: str = "past_projection_locked"
    offending_week_starts: list[date]
    detail: str
