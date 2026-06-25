from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ParsedVisitOut(BaseModel):
    """One row of parsed_visits, suitable for the SoA review table."""

    name: str
    visit_type: Literal["screening", "randomization", "follow_up", "other"]
    target_day_offset: int
    window_days: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    flagged_reason: str | None = None


class SoaParseJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    trial_id: UUID | None
    status: str
    model_id: str | None
    prompt_version: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class SoaParseJobDetailOut(SoaParseJobOut):
    """Full payload including parsed_visits — used by the wizard's review step."""

    parsed_visits: list[ParsedVisitOut] | None = None


class SoaParseJobApplyIn(BaseModel):
    """User-edited visits sent to /parse-jobs/{id}/apply."""

    arm_id: UUID
    # The user may have edited names, day offsets, types, windows, etc. before
    # applying. We accept the full payload back rather than just "use what's
    # stored" — that's the whole point of the review step.
    visits: list[ParsedVisitOut]
    # When True, a snapshot of the arm's existing visits is taken and then
    # every existing visit on the arm is deleted before the new ones are
    # written. The default (False) appends, matching the wizard's "create
    # new trial" flow where the arm starts empty. Re-parses from
    # TrialDetail set this to True so the user gets a clean redo.
    replace_existing: bool = False
