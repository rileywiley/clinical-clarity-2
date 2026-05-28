"""EnrollmentWeek + EnrollmentWeekHistory (PRD §5.1, §7.3).

One row per (site, trial, arm, site-local Monday). Backs the projection-entry
grid directly. Audit trail records **projection edits only** — actuals overwrite,
they don't "change a plan," so they're not in the history.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class EnrollmentWeek(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "enrollment_weeks"
    __table_args__ = (
        UniqueConstraint(
            "site_id",
            "trial_id",
            "arm_id",
            "week_start",
            name="uq_enrollment_weeks_site_trial_arm_week",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    site_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trial_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    arm_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("arms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    proj_screened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proj_randomized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_screened: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_randomized: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EnrollmentWeekHistory(Base, OrgScopedMixin):
    """Append-only audit trail. One row per *changed* projection field per save.

    Actuals are not audited (PRD §5.1: history is for projections — the planning
    record). The change recording lives in app/services/enrollment_audit.py.
    """

    __tablename__ = "enrollment_week_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    enrollment_week_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("enrollment_weeks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
