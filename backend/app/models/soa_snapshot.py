from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, new_uuid


class SoaSnapshot(Base, OrgScopedMixin):
    """Point-in-time copy of a trial's SoA (post-Phase-6).

    Created automatically by the apply-parse-job endpoint when re-parsing
    onto an existing trial (so the user can revert a bad LLM redo), and
    manually from the TrialDetail edit-mode header. Restore writes the
    snapshot's visits back to the arm, after taking a fresh snapshot of
    the current state — restores are themselves reversible.
    """

    __tablename__ = "soa_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    trial_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # "reparse_replace" — taken just before a re-parse replaced the SoA.
    # "manual" — the user clicked "Save snapshot" on the edit screen.
    # "pre_restore" — taken automatically before a Restore writes the
    # picked snapshot back; gives users a way to undo a bad restore.
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Visits as JSONB — see migration 0007 for the shape.
    visits: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # Snapshots are immutable — no updated_at, only created_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
