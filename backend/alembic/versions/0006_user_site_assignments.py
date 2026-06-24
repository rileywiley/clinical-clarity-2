"""phase 6 — user_site_assignments

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-24

Adds the many-to-many between users and sites that backs site-scoped roles
(Site Manager / Viewer). The relationship was conceptually planned in Phase 0
but no migration shipped — the Admin Settings page in Phase 6 needs it.

Org-scoped with the same tenant_isolation policy shape as every other
domain table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)

    op.create_table(
        "user_site_assignments",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            pg_uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            pg_uuid,
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id", "site_id", name="uq_user_site_assignments_user_site"
        ),
    )
    op.create_index(
        "ix_user_site_assignments_org_id", "user_site_assignments", ["org_id"]
    )
    op.create_index(
        "ix_user_site_assignments_user_id", "user_site_assignments", ["user_id"]
    )
    op.create_index(
        "ix_user_site_assignments_site_id", "user_site_assignments", ["site_id"]
    )

    op.execute("ALTER TABLE user_site_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_site_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY user_site_assignments_tenant_isolation ON user_site_assignments
            USING (org_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_site_assignments CASCADE")
