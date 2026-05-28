"""phase 3 enrollment weeks + history

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-28

Adds the projection-entry backing tables (PRD §5.1, §7.3):
- enrollment_weeks: one row per (site, trial, arm, week_start), unique on those four.
- enrollment_week_history: append-only audit trail for projection edits.

Both are org-scoped with the same RLS policy shape as the rest of the domain.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_isolation ON {table}
            USING (org_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """
    )


def upgrade() -> None:
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)

    # --- enrollment_weeks --------------------------------------------------
    op.create_table(
        "enrollment_weeks",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            pg_uuid,
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trial_id",
            pg_uuid,
            sa.ForeignKey("trials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "arm_id",
            pg_uuid,
            sa.ForeignKey("arms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("proj_screened", sa.Integer, nullable=False, server_default="0"),
        sa.Column("proj_randomized", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actual_screened", sa.Integer, nullable=True),
        sa.Column("actual_randomized", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "site_id", "trial_id", "arm_id", "week_start",
            name="uq_enrollment_weeks_site_trial_arm_week",
        ),
    )
    op.create_index("ix_enrollment_weeks_org_id", "enrollment_weeks", ["org_id"])
    op.create_index("ix_enrollment_weeks_site_id", "enrollment_weeks", ["site_id"])
    op.create_index("ix_enrollment_weeks_trial_id", "enrollment_weeks", ["trial_id"])
    op.create_index("ix_enrollment_weeks_arm_id", "enrollment_weeks", ["arm_id"])
    op.create_index("ix_enrollment_weeks_week_start", "enrollment_weeks", ["week_start"])
    _enable_tenant_rls("enrollment_weeks")

    # --- enrollment_week_history ------------------------------------------
    op.create_table(
        "enrollment_week_history",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_week_id",
            pg_uuid,
            sa.ForeignKey("enrollment_weeks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(40), nullable=False),
        sa.Column("old_value", sa.Integer, nullable=True),
        sa.Column("new_value", sa.Integer, nullable=True),
        sa.Column(
            "changed_by",
            pg_uuid,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_enrollment_week_history_org_id", "enrollment_week_history", ["org_id"])
    op.create_index(
        "ix_enrollment_week_history_enrollment_week_id",
        "enrollment_week_history",
        ["enrollment_week_id"],
    )
    _enable_tenant_rls("enrollment_week_history")

    # Grants for the runtime role on the new tables.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")


def downgrade() -> None:
    for table in ("enrollment_week_history", "enrollment_weeks"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
