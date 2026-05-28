from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class OrgSignupIn(BaseModel):
    """Phase 0 onboarding: create an org and its initial Org Admin user in one call.

    This is the seam Phase 6 will replace with a real new-org onboarding flow.
    """

    org_name: str = Field(min_length=1, max_length=200)
    default_timezone: str = "UTC"
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    admin_name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    id: UUID
    name: str
    default_timezone: str
    currency: str
