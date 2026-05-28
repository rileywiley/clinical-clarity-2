from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SiteTrialIn(BaseModel):
    site_id: UUID
    per_site_enrollment_target: int = Field(default=0, ge=0)
    per_site_screening_target: int = Field(default=0, ge=0)
    active: bool = True


class SiteTrialPatch(BaseModel):
    per_site_enrollment_target: int | None = Field(default=None, ge=0)
    per_site_screening_target: int | None = Field(default=None, ge=0)
    active: bool | None = None


class SiteTrialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    trial_id: UUID
    per_site_enrollment_target: int
    per_site_screening_target: int
    active: bool


class VisitOverrideIn(BaseModel):
    visit_id: UUID
    duration_hours: float = Field(gt=0)


class VisitOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_trial_id: UUID
    visit_id: UUID
    duration_hours: float
