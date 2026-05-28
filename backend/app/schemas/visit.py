from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.visit import VisitType


class VisitIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    visit_type: VisitType
    target_day_offset: int
    window_days: int = Field(default=0, ge=0)
    duration_hours_override: float | None = Field(default=None, ge=0)
    # PRD §10.1: cost is structure-only in v1. The API accepts it (per the
    # saved decision), but no endpoint reads it back as a margin metric.
    price: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0)


class VisitPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    visit_type: VisitType | None = None
    target_day_offset: int | None = None
    window_days: int | None = Field(default=None, ge=0)
    duration_hours_override: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None, ge=0)


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    arm_id: UUID
    name: str
    visit_type: VisitType
    target_day_offset: int
    window_days: int
    duration_hours_override: float | None
    price: float | None
    cost: float | None
    sort_order: int
