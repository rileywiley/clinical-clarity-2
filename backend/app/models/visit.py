from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Enum, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class VisitType(enum.StrEnum):
    SCREENING = "screening"
    RANDOMIZATION = "randomization"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class Visit(Base, OrgScopedMixin, TimestampMixin):
    """One SoA row, per arm (PRD §5.1).

    ``duration_hours_override`` left null = inherit org type default *live*
    (PRD §5.2). The same applies to ``price`` (null until pricing step) and
    ``cost`` (structure-only in v1 per PRD §10.1 / CLAUDE.md — the field is
    persisted but no endpoint reads it back as a margin metric).
    """

    __tablename__ = "visits"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    arm_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("arms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    visit_type: Mapped[VisitType] = mapped_column(
        Enum(VisitType, name="visit_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    target_day_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_hours_override: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # PRD §10.2: when AI populated this row, ``confidence`` is the parser's
    # self-reported score (0..1). NULL means the row was entered by a human
    # (or pre-AI). ``flagged_reason`` is the short label the SoA review table
    # shows next to amber/red rows.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    flagged_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
