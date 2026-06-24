"""UserSiteAssignment (PRD §3, §5.1).

Many-to-many between users and sites for site-scoped roles. Site Manager
and Viewer roles see only their assigned sites; Org Admin and Ops Lead see
all sites in the org (assignments are ignored for them at the query layer).

Unique on (user_id, site_id) so the same user can't be assigned to the same
site twice, but a user can have many sites and a site can have many users.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class UserSiteAssignment(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "user_site_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_user_site_assignments_user_site"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
