"""phase 5 — documents + soa_parse_jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-24

Adds the two Phase 5 tables backing AI SoA parsing:
- documents: uploaded files (storage_key is opaque, points at S3/MinIO)
- soa_parse_jobs: per-document parse runs; parsed_visits stays in JSONB until
  the user applies, so unconfirmed AI output never reaches the engine

Both org-scoped with the same tenant_isolation policy shape as Phases 2–3.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_KIND_VALUES = ("protocol_pdf",)
DOCUMENT_STATUS_VALUES = ("uploaded", "parsing", "parsed", "discarded")
PARSE_JOB_STATUS_VALUES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "applied",
    "discarded",
)


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

    # --- documents --------------------------------------------------------
    op.create_table(
        "documents",
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
            sa.ForeignKey("trials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kind",
            sa.Enum(*DOCUMENT_KIND_VALUES, name="document_kind"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column(
            "uploaded_by",
            pg_uuid,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(*DOCUMENT_STATUS_VALUES, name="document_status"),
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])
    op.create_index("ix_documents_trial_id", "documents", ["trial_id"])
    _enable_tenant_rls("documents")

    # --- soa_parse_jobs ---------------------------------------------------
    op.create_table(
        "soa_parse_jobs",
        sa.Column("id", pg_uuid, primary_key=True),
        sa.Column(
            "org_id",
            pg_uuid,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            pg_uuid,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trial_id",
            pg_uuid,
            sa.ForeignKey("trials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(*PARSE_JOB_STATUS_VALUES, name="soa_parse_job_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("raw_output", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("parsed_visits", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_soa_parse_jobs_org_id", "soa_parse_jobs", ["org_id"])
    op.create_index("ix_soa_parse_jobs_document_id", "soa_parse_jobs", ["document_id"])
    op.create_index("ix_soa_parse_jobs_trial_id", "soa_parse_jobs", ["trial_id"])
    _enable_tenant_rls("soa_parse_jobs")

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user"
    )


def downgrade() -> None:
    for t in ("soa_parse_jobs", "documents"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    sa.Enum(name="soa_parse_job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="document_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="document_kind").drop(op.get_bind(), checkfirst=True)
