"""OrgSettings — every tunable default the Admin settings page exposes.

PRD §5.1 / §5.2: values resolve **live** at compute/render time. Changing a
type-default duration here re-flows immediately to every trial/visit that
inherits it (i.e. has no explicit override). The engine remains pure (CLAUDE.md
golden rule #2): the backend resolves these on each forecast run and passes
them as plain dataclasses into the engine.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class OrgSettings(Base, OrgScopedMixin, TimestampMixin):
    """One row per org. Carries `org_id` and is RLS-protected so an admin can
    only see/modify their own org's settings."""

    __tablename__ = "org_settings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)

    # --- Forecasting defaults (PRD §5.1 OrgSettings, durations in hours) ---
    dur_screening_hours: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=5.0
    )
    dur_randomization_hours: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=4.0
    )
    dur_follow_up_hours: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=2.0
    )
    dur_other_hours: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=3.0
    )

    # --- Display defaults --------------------------------------------------
    util_threshold_green_max: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=70.0
    )
    util_threshold_amber_max: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=95.0
    )
    default_grid_weeks_visible: Mapped[int] = mapped_column(nullable=False, default=12)
    default_horizon_months: Mapped[int] = mapped_column(nullable=False, default=18)

    # --- Org defaults ------------------------------------------------------
    default_site_hours_per_day: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=10.0
    )
    # Default attrition curve for new trials. Set after seeding so the FK is real.
    default_attrition_curve_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attrition_curves.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Display-only currency placeholder (USD-locked in v1; field exists for
    # future multi-currency — PRD §4.5).
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
