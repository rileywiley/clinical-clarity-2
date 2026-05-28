from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttritionCurveIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    total_dropout_pct: float = Field(ge=0, lt=1)
    shape: str = "linear_backloaded"


class AttritionCurvePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    total_dropout_pct: float | None = Field(default=None, ge=0, lt=1)
    shape: str | None = None


class AttritionCurveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID | None
    name: str
    total_dropout_pct: float
    shape: str
    is_preset: bool
