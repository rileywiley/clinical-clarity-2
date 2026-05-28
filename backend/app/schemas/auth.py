from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    # An org admin can have the same email across orgs (email is unique per-org),
    # so the client picks which org to authenticate against.
    org_id: UUID


class MeOut(BaseModel):
    user_id: UUID
    org_id: UUID
    email: EmailStr
    name: str
    role: UserRole
