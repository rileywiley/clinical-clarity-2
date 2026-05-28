"""init orgs, users, and RLS policies

Revision ID: 0001
Revises:
Create Date: 2026-05-28

Creates the Phase 0 schema (organizations, users) and the RLS policies that scope
``users`` (and every future ``OrgScopedMixin`` table) to ``current_setting('app.current_org_id')``.

This migration assumes the runtime role ``app_user`` already exists. The Docker
init script creates it; in CI the test fixture creates it before running migrations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


USER_ROLE_VALUES = ("org_admin", "ops_lead", "site_manager", "viewer")


def upgrade() -> None:
    # --- Extensions ---------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # --- organizations ------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("default_timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- users --------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.Enum(*USER_ROLE_VALUES, name="user_role"), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])

    # --- RLS ----------------------------------------------------------------
    # Tenant scoping on `users`. Future migrations install the same pair of policies
    # on every OrgScopedMixin table. `organizations` itself is scoped by id, not org_id.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY users_tenant_isolation ON users
            USING (org_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """
    )

    # `organizations` is also scoped: the only org you may read is the one bound to
    # your session. This stops cross-org enumeration via /orgs/me or future endpoints.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organizations_self_only ON organizations
            USING (id::text = current_setting('app.current_org_id', true))
            WITH CHECK (id::text = current_setting('app.current_org_id', true))
        """
    )

    # Grants for the runtime role. app_owner (which runs this migration) has
    # BYPASSRLS, so it is unaffected by the policies above.
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_self_only ON organizations")
    op.execute("DROP POLICY IF EXISTS users_tenant_isolation ON users")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
