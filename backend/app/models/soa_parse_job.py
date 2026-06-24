"""SoaParseJob (PRD §10.2).

One row per parse run. The job's structured output (``parsed_visits``) lives in
JSONB so the user can review and edit before applying. PRD §10.2 mitigation:
parser output never flows into forecast math unconfirmed — that's enforced
structurally by *not* writing Visit rows until the user explicitly applies.

``raw_output`` keeps the full Claude response so we can replay against later
prompt revisions or audit decisions later.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class SoaParseJobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    APPLIED = "applied"
    DISCARDED = "discarded"


class SoaParseJob(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "soa_parse_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trial_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[SoaParseJobStatus] = mapped_column(
        Enum(
            SoaParseJobStatus,
            name="soa_parse_job_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SoaParseJobStatus.QUEUED,
    )
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Full Claude response (or relevant subset). Kept so a stored job can be
    # replayed against a newer prompt or model later without re-billing.
    raw_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Structured visits: [{name, visit_type, target_day_offset, window_days,
    #                      duration_hours_override, price, confidence,
    #                      flagged_reason}, ...]
    # This is what the SoA review table renders + edits. On apply, these
    # become Visit rows on the trial's arm.
    parsed_visits: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
