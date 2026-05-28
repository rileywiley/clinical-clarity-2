from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class TrialStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Trial(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "trials"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sponsor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    protocol_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[TrialStatus] = mapped_column(
        Enum(TrialStatus, name="trial_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=TrialStatus.DRAFT,
    )
    fpfv: Mapped[date] = mapped_column(Date, nullable=False)
    lpfv: Mapped[date] = mapped_column(Date, nullable=False)
    lplv: Mapped[date] = mapped_column(Date, nullable=False)
    is_multi_arm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Both targets — PRD §9.2 Phase 2 explicitly calls for tracking both.
    enrollment_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    screening_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attrition_curve_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attrition_curves.id", ondelete="SET NULL"),
        nullable=True,
    )
    pending_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Arm(Base, OrgScopedMixin, TimestampMixin):
    """Single-arm trials get one auto-created 'Default Arm' so the UI never
    forces arm-thinking unless `is_multi_arm` (PRD §5.1)."""

    __tablename__ = "arms"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    trial_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Default Arm")
