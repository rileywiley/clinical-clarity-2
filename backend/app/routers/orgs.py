"""Org signup + scoped reads.

Signup is intentionally simple in Phase 0: one call creates the tenant root and its
first Org Admin. Phase 6 will replace this with a real new-org onboarding flow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, get_db_unscoped, require_role
from app.models.attrition_curve import AttritionCurve
from app.models.base import new_uuid
from app.models.org import Organization
from app.models.org_settings import OrgSettings
from app.models.user import User, UserRole
from app.schemas.org import OrgOut, OrgSignupIn
from app.security import hash_password

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrgOut)
async def signup(
    payload: OrgSignupIn,
    db: AsyncSession = Depends(get_db_unscoped),
) -> Organization:
    # The org and its admin user are written under app_user, which is RLS-bound.
    # Both `organizations` and `users` have WITH CHECK policies tied to
    # current_setting('app.current_org_id'), so we must:
    #   1. mint the org id up front,
    #   2. set the tenant to that id,
    #   3. insert both rows in that scope.
    # The org id is server-generated; primary-key uniqueness blocks any attempt
    # to claim an existing org.
    org_id = new_uuid()
    await db.execute(
        text("SELECT set_config('app.current_org_id', :v, true)"),
        {"v": str(org_id)},
    )
    org = Organization(
        id=org_id,
        name=payload.org_name,
        default_timezone=payload.default_timezone,
    )
    db.add(org)
    await db.flush()  # ordering: org must exist before the user FK is satisfied

    admin = User(
        org_id=org.id,
        email=payload.admin_email,
        password_hash=hash_password(payload.admin_password),
        name=payload.admin_name,
        role=UserRole.ORG_ADMIN,
    )
    db.add(admin)

    # Phase 2 seed: every new org gets the three attrition presets (Low /
    # Standard / High) and an OrgSettings row, with Standard as the default
    # curve. PRD §5.1 defaults — chosen to be conservative-on-screening per
    # the engine modeling decisions.
    low = AttritionCurve(
        org_id=org.id, name="Low", total_dropout_pct=0.10, is_preset=True
    )
    standard = AttritionCurve(
        org_id=org.id, name="Standard", total_dropout_pct=0.20, is_preset=True
    )
    high = AttritionCurve(
        org_id=org.id, name="High", total_dropout_pct=0.35, is_preset=True
    )
    db.add_all([low, standard, high])
    await db.flush()  # standard.id is needed for OrgSettings.default_attrition_curve_id

    settings = OrgSettings(org_id=org.id, default_attrition_curve_id=standard.id)
    db.add(settings)

    return org


@router.get("/me", response_model=OrgOut)
async def my_org(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    # RLS guarantees we can only see our own org row.
    org = await db.get(Organization, user.org_id)
    assert org is not None  # invariant: user.org_id is valid; RLS enforces visibility
    return org


@router.get("/admin-only", dependencies=[Depends(require_role(UserRole.ORG_ADMIN))])
async def admin_only_probe() -> dict[str, str]:
    """Stub route used by the Phase 0 gate test to prove role gating works."""
    return {"ok": "true"}
