"""Declarative base + reusable mixins.

``OrgScopedMixin`` is the structural enforcement of CLAUDE.md golden rule #6:
"every table carries org_id". Future domain tables (Site, Trial, Visit, ...) must
inherit it. The Phase 0 RLS migration installs policies that read ``org_id`` from
this column, so getting the column name wrong on a table = the table is unprotected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class OrgScopedMixin:
    """Marks an entity as tenant-scoped. The RLS migration creates a policy on every
    table that inherits this mixin."""

    @declared_attr.directive
    def org_id(cls) -> Mapped[UUID]:
        return mapped_column(
            PG_UUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


def new_uuid() -> UUID:
    return uuid4()
