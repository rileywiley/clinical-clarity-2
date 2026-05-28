"""phase 2 core entities

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-28

Adds the Phase 2 domain tables (PRD §5.1) and their RLS policies:
- org_settings (1:1 with organizations)
- attrition_curves (org_id nullable for global seeds; policy permits NULL)
- sites
- trials, arms, visits
- site_trials, site_trial_visit_overrides

Every org-scoped table gets a tenant_isolation policy following the same shape
as the Phase 0 users policy: `org_id::text = current_setting('app.current_org_id', true)`.
The attrition_curves policy is wider (allows NULL org_id rows) to support
future global seeds.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIAL_STATUS_VALUES = ("draft", "active", "archived")
VISIT_TYPE_VALUES = ("screening", "randomization", "follow_up", "other")

ORG_SCOPED_TABLES = (
    "org_settings",
    "sites",
    "trials",
    "arms",
    "visits",
    "site_trials",
    "site_trial_visit_overrides",
)


def _enable_tenant_rls(table: str) -> None:
    """Standard 'org_id matches bound tenant' policy. Used for every
    OrgScopedMixin table."""
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

    # --- attrition_curves --------------------------------------------------
    # Note: org_id nullable here (for future global seeds). The policy below
    # permits a row when its org_id matches the bound tenant OR is NULL.
    op.create_table(
        "attrition_curves",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("total_dropout_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("shape", sa.String(50), nullable=False, server_default="linear_backloaded"),
        sa.Column("is_preset", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_attrition_curves_org_id", "attrition_curves", ["org_id"])
    op.execute("ALTER TABLE attrition_curves ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attrition_curves FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY attrition_curves_tenant_or_global ON attrition_curves
            USING (
                org_id IS NULL
                OR org_id::text = current_setting('app.current_org_id', true)
            )
            WITH CHECK (
                org_id::text = current_setting('app.current_org_id', true)
            )
        """
    )

    # --- org_settings ------------------------------------------------------
    op.create_table(
        "org_settings",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("dur_screening_hours", sa.Numeric(6, 2), nullable=False, server_default="5.0"),
        sa.Column("dur_randomization_hours", sa.Numeric(6, 2), nullable=False, server_default="4.0"),
        sa.Column("dur_follow_up_hours", sa.Numeric(6, 2), nullable=False, server_default="2.0"),
        sa.Column("dur_other_hours", sa.Numeric(6, 2), nullable=False, server_default="3.0"),
        sa.Column("util_threshold_green_max", sa.Numeric(5, 2), nullable=False, server_default="70.0"),
        sa.Column("util_threshold_amber_max", sa.Numeric(5, 2), nullable=False, server_default="95.0"),
        sa.Column("default_grid_weeks_visible", sa.Integer, nullable=False, server_default="12"),
        sa.Column("default_horizon_months", sa.Integer, nullable=False, server_default="18"),
        sa.Column("default_site_hours_per_day", sa.Numeric(5, 2), nullable=False, server_default="10.0"),
        sa.Column(
            "default_attrition_curve_id",
            pg_uuid,
            sa.ForeignKey("attrition_curves.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_org_settings_org_id", "org_settings", ["org_id"])
    _enable_tenant_rls("org_settings")

    # --- sites -------------------------------------------------------------
    op.create_table(
        "sites",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "operating_weekdays",
            sa.dialects.postgresql.ARRAY(sa.Integer),
            nullable=False,
            server_default="{0,1,2,3,4}",
        ),
        sa.Column("hours_per_day", sa.Numeric(5, 2), nullable=False, server_default="10.0"),
        sa.Column("rooms", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sites_org_id", "sites", ["org_id"])
    _enable_tenant_rls("sites")

    # --- trials ------------------------------------------------------------
    op.create_table(
        "trials",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sponsor", sa.String(200), nullable=True),
        sa.Column("protocol_ref", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*TRIAL_STATUS_VALUES, name="trial_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("fpfv", sa.Date, nullable=False),
        sa.Column("lpfv", sa.Date, nullable=False),
        sa.Column("lplv", sa.Date, nullable=False),
        sa.Column("is_multi_arm", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("enrollment_target", sa.Integer, nullable=False, server_default="0"),
        sa.Column("screening_target", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "attrition_curve_id",
            pg_uuid,
            sa.ForeignKey("attrition_curves.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pending_amendment", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trials_org_id", "trials", ["org_id"])
    _enable_tenant_rls("trials")

    # --- arms --------------------------------------------------------------
    op.create_table(
        "arms",
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
        sa.Column("name", sa.String(200), nullable=False, server_default="Default Arm"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_arms_org_id", "arms", ["org_id"])
    op.create_index("ix_arms_trial_id", "arms", ["trial_id"])
    _enable_tenant_rls("arms")

    # --- visits ------------------------------------------------------------
    op.create_table(
        "visits",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "arm_id",
            pg_uuid,
            sa.ForeignKey("arms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "visit_type",
            sa.Enum(*VISIT_TYPE_VALUES, name="visit_type"),
            nullable=False,
        ),
        sa.Column("target_day_offset", sa.Integer, nullable=False),
        sa.Column("window_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_hours_override", sa.Numeric(6, 2), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_visits_org_id", "visits", ["org_id"])
    op.create_index("ix_visits_arm_id", "visits", ["arm_id"])
    _enable_tenant_rls("visits")

    # --- site_trials -------------------------------------------------------
    op.create_table(
        "site_trials",
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
        sa.Column("per_site_enrollment_target", sa.Integer, nullable=False, server_default="0"),
        sa.Column("per_site_screening_target", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "trial_id", name="uq_site_trials_site_trial"),
    )
    op.create_index("ix_site_trials_org_id", "site_trials", ["org_id"])
    op.create_index("ix_site_trials_site_id", "site_trials", ["site_id"])
    op.create_index("ix_site_trials_trial_id", "site_trials", ["trial_id"])
    _enable_tenant_rls("site_trials")

    # --- site_trial_visit_overrides ----------------------------------------
    op.create_table(
        "site_trial_visit_overrides",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_trial_id",
            pg_uuid,
            sa.ForeignKey("site_trials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "visit_id",
            pg_uuid,
            sa.ForeignKey("visits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("duration_hours", sa.Numeric(6, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("site_trial_id", "visit_id", name="uq_stvo_site_trial_visit"),
    )
    op.create_index(
        "ix_site_trial_visit_overrides_org_id", "site_trial_visit_overrides", ["org_id"]
    )
    _enable_tenant_rls("site_trial_visit_overrides")

    # Grants for the runtime role on the new tables.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")


def downgrade() -> None:
    # Drop in reverse FK order. Policies drop automatically with the tables.
    for table in (
        "site_trial_visit_overrides",
        "site_trials",
        "visits",
        "arms",
        "trials",
        "sites",
        "org_settings",
        "attrition_curves",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    sa.Enum(name="visit_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="trial_status").drop(op.get_bind(), checkfirst=True)
