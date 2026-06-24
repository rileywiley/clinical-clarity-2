from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    name: str
    role: UserRole
    active: bool


class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8)
    role: UserRole = UserRole.VIEWER


class UserPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    active: bool | None = None
    # Password reset is intentionally not in v1 — would need a separate flow
    # (token email, current-password check). Phase 6 scope keeps it out.


class SiteUserAssignmentIn(BaseModel):
    user_id: UUID


class SiteUserOut(BaseModel):
    """User row enriched with assignment id, used by the site-detail user list."""

    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    user_id: UUID
    email: EmailStr
    name: str
    role: UserRole
