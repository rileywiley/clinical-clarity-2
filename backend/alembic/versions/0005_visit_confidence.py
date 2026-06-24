"""phase 5 — visit confidence + flagged reason

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-24

Adds the two columns that let the SoA review table distinguish AI-populated
rows from human-entered ones (NULL confidence = human / pre-AI). Both nullable
so legacy Phase 2 visits don't need backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("confidence", sa.Float, nullable=True))
    op.add_column("visits", sa.Column("flagged_reason", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "flagged_reason")
    op.drop_column("visits", "confidence")
