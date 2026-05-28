from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArmIn(BaseModel):
    name: str = Field(min_length=1, max_length=200, default="Default Arm")


class ArmPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ArmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trial_id: UUID
    name: str
