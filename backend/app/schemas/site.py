from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: str = Field(min_length=1, max_length=64)
    operating_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    hours_per_day: float = Field(default=10.0, gt=0, le=24)
    rooms: int = Field(default=1, ge=1)
    active: bool = True

    @field_validator("operating_weekdays")
    @classmethod
    def _check_weekdays(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("operating_weekdays must be non-empty")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("operating_weekdays values must be in 0..6 (Mon=0)")
        return sorted(set(v))


class SitePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    operating_weekdays: list[int] | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    rooms: int | None = Field(default=None, ge=1)
    active: bool | None = None

    @field_validator("operating_weekdays")
    @classmethod
    def _check_weekdays(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("operating_weekdays must be non-empty")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("operating_weekdays values must be in 0..6 (Mon=0)")
        return sorted(set(v))


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str | None
    timezone: str
    operating_weekdays: list[int]
    hours_per_day: float
    rooms: int
    active: bool
