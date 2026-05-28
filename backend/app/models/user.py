from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class UserRole(enum.StrEnum):
    """Roles per PRD §3. Scoping is site-level only — no trial-level roles in v1."""

    ORG_ADMIN = "org_admin"
    OPS_LEAD = "ops_lead"
    SITE_MANAGER = "site_manager"
    VIEWER = "viewer"


class User(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # Email is unique *per org* (PRD §5.1), not globally — different orgs can share
        # an email without colliding.
        UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        # values_callable: store the str values ("org_admin"), not the Python
        # enum member names ("ORG_ADMIN") — the Postgres enum was created with
        # the lowercase values.
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.VIEWER,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
