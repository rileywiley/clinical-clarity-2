"""AttritionCurve — per-trial attrition shape (PRD §5.1).

Seeded presets per org: Low (10%), Standard (20%), High (35%). `org_id` is
nullable to allow future global seeds; the v1 RLS policy lets a row through
when its `org_id` matches the bound tenant OR is NULL (global). v1 ships with
per-org seeds only — global seeds aren't used yet but the column shape is in
place for v1.5.

The `shape` field is a string for v1; we ship one value (`linear_backloaded`)
matching the engine's hardcoded shape (see project memory: engine modeling
decisions). Future shapes would be additive enum values + a different engine
branch.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class AttritionCurve(Base, TimestampMixin):
    """Not OrgScopedMixin — org_id is nullable here (global seeds), so we
    define the column explicitly and add the partial RLS policy in the
    migration."""

    __tablename__ = "attrition_curves"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    org_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    total_dropout_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    shape: Mapped[str] = mapped_column(
        String(50), nullable=False, default="linear_backloaded"
    )
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
