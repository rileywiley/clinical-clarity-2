"""post-p6 — soa_snapshots

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-24

A point-in-time copy of a trial's SoA (visit rows), stored as JSONB.
Created automatically before a re-parse-replace, and manually on demand
from the TrialDetail page. Restore writes the snapshot's visits back
onto the arm (after first taking a snapshot of the current state, so
restores are themselves reversible).

Org-scoped + RLS like every other domain table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)
    pg_jsonb = sa.dialects.postgresql.JSONB

    op.create_table(
        "soa_snapshots",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trial_id",
            pg_uuid,
            sa.ForeignKey("trials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            pg_uuid,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # "reparse_replace" | "manual" | "pre_restore"
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        # Snapshot of every Visit on every Arm of the trial at this moment.
        # Shape: [{arm_id, arm_name, name, visit_type, target_day_offset,
        #          window_days, duration_hours_override, price, cost,
        #          sort_order, confidence, flagged_reason}, ...]
        sa.Column("visits", pg_jsonb, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_soa_snapshots_org_id", "soa_snapshots", ["org_id"])
    op.create_index("ix_soa_snapshots_trial_id", "soa_snapshots", ["trial_id"])

    op.execute("ALTER TABLE soa_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE soa_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY soa_snapshots_tenant_isolation ON soa_snapshots
            USING (org_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (org_id::text = current_setting('app.current_org_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS soa_snapshots CASCADE")
