"""Document model (PRD §7.1 / §10.2).

An uploaded file owned by an org, optionally attached to a trial. Phase 5 ships
one ``kind``: ``protocol_pdf``. The storage_key is opaque — points at an S3
object that lives outside the DB.
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin, new_uuid


class DocumentKind(enum.StrEnum):
    PROTOCOL_PDF = "protocol_pdf"


class DocumentStatus(enum.StrEnum):
    """Lifecycle. PRD §10.2 mitigation: a doc is ``uploaded`` until a parse
    job is enqueued; ``parsed`` once a parse job applied; ``stale`` if the
    user discarded the parse output."""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    DISCARDED = "discarded"


class Document(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    # trial_id is nullable so users can upload a doc, then attach it to a trial
    # later. Phase 5's wizard always uploads with the trial already created.
    trial_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="document_kind", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
