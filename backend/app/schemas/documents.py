from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trial_id: UUID | None
    kind: str
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_by: UUID | None
    created_at: datetime
