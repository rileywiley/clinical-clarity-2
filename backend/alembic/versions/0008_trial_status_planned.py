"""add 'planned' to trial_status enum

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-25

Adds a fourth trial status, ``planned``, between ``draft`` and ``active`` in the
lifecycle (PRD §6.9 / §7.1). A planned trial is fully configured and forecast-
ready but scheduled to start in the future; it is reported separately from
active so the forecast can split committed (active) from pipeline (planned)
volume.

Postgres can ADD a value to an existing enum but cannot DROP one, so the
downgrade is a deliberate no-op (documented below). On PostgreSQL 12+ the
``ADD VALUE`` runs fine inside Alembic's per-migration transaction because the
new value is not used within this same migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # BEFORE 'active' keeps the enum's stored order aligned with the lifecycle
    # (draft → planned → active → archived). Functionally the app never relies on
    # enum sort order — it filters by equality/IN and sorts in Python — but the
    # ordering keeps psql introspection readable.
    op.execute("ALTER TYPE trial_status ADD VALUE IF NOT EXISTS 'planned' BEFORE 'active'")


def downgrade() -> None:
    # No-op: PostgreSQL has no DROP VALUE for enums. Removing 'planned' would
    # require rebuilding the type (rename old, create new without the value,
    # rewrite the column, drop old) and would fail if any trial row still uses
    # it. We accept a one-way migration here rather than carry that risk.
    pass
