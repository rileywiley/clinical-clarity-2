from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class Site(Base, OrgScopedMixin, TimestampMixin):
    """A trial site (PRD §5.1).

    ``operating_weekdays`` is stored as a Postgres array of smallint where each
    value is a Python weekday index (Mon=0..Sun=6). The API validates that the
    array is a subset of {0..6} and non-empty.
    """

    __tablename__ = "sites"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    operating_weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [0, 1, 2, 3, 4]
    )
    hours_per_day: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=10.0
    )
    rooms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
