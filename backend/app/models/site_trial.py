from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class SiteTrial(Base, OrgScopedMixin, TimestampMixin):
    """A trial assigned to a site (PRD §5.1).

    Carries the *per-site* targets — these can differ from the trial-level
    totals (e.g. a multi-site trial split unevenly across sites).
    """

    __tablename__ = "site_trials"
    __table_args__ = (UniqueConstraint("site_id", "trial_id", name="uq_site_trials_site_trial"),)

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
    per_site_enrollment_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    per_site_screening_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteTrialVisitOverride(Base, OrgScopedMixin, TimestampMixin):
    """Per-(site, visit) duration override (PRD §5.1).

    Highest-priority layer in the §5.2 resolution order.
    """

    __tablename__ = "site_trial_visit_overrides"
    __table_args__ = (
        UniqueConstraint(
            "site_trial_id", "visit_id", name="uq_stvo_site_trial_visit"
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    site_trial_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("site_trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visit_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("visits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    duration_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
