from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.trial import TrialStatus


class TrialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sponsor: str | None = Field(default=None, max_length=200)
    protocol_ref: str | None = Field(default=None, max_length=200)
    fpfv: date
    lpfv: date
    lplv: date
    is_multi_arm: bool = False
    enrollment_target: int = Field(default=0, ge=0)
    screening_target: int = Field(default=0, ge=0)
    attrition_curve_id: UUID | None = None

    @model_validator(mode="after")
    def _check_date_order(self) -> TrialIn:
        if not (self.fpfv <= self.lpfv <= self.lplv):
            raise ValueError("fpfv ≤ lpfv ≤ lplv must hold")
        return self


class TrialPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sponsor: str | None = Field(default=None, max_length=200)
    protocol_ref: str | None = Field(default=None, max_length=200)
    fpfv: date | None = None
    lpfv: date | None = None
    lplv: date | None = None
    enrollment_target: int | None = Field(default=None, ge=0)
    screening_target: int | None = Field(default=None, ge=0)
    attrition_curve_id: UUID | None = None
    pending_amendment: bool | None = None


class TrialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sponsor: str | None
    protocol_ref: str | None
    status: TrialStatus
    fpfv: date
    lpfv: date
    lplv: date
    is_multi_arm: bool
    enrollment_target: int
    screening_target: int
    attrition_curve_id: UUID | None
    pending_amendment: bool


class TrialActivationFailureOut(BaseModel):
    reason: str
    detail: str


class TrialActivationErrorOut(BaseModel):
    """Surface every prerequisite failure at once (better wizard UX)."""

    failures: list[TrialActivationFailureOut]
