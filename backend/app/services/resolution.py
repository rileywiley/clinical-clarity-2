"""Live-resolved defaults (PRD §5.2).

Mirrors the shape of ``engine/duration.py`` but reads from the DB. Resolution
order, first non-null wins:

1. SiteTrialVisitOverride.duration_hours (per-site override)
2. Visit.duration_hours_override (per-visit override)
3. OrgSettings type default for the visit's type — read **live** so a change
   in OrgSettings immediately re-flows.

The Phase 4 wiring will call ``org_duration_defaults(org_id)`` once per
forecast run, then hand the resulting dataclass into the engine. The engine
itself never touches the DB (CLAUDE.md golden rule #2).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_settings import OrgSettings
from app.models.site_trial import SiteTrialVisitOverride
from app.models.visit import Visit, VisitType


def _type_default(settings: OrgSettings, vt: VisitType) -> float:
    match vt:
        case VisitType.SCREENING:
            return float(settings.dur_screening_hours)
        case VisitType.RANDOMIZATION:
            return float(settings.dur_randomization_hours)
        case VisitType.FOLLOW_UP:
            return float(settings.dur_follow_up_hours)
        case VisitType.OTHER:
            return float(settings.dur_other_hours)


async def get_org_settings(db: AsyncSession, org_id: UUID) -> OrgSettings:
    """Fetch this org's settings. Raises if missing (every org has one row;
    signup ensures it). RLS guarantees we only see our own."""
    s = (
        await db.execute(select(OrgSettings).where(OrgSettings.org_id == org_id))
    ).scalar_one()
    return s


async def resolve_visit_duration(
    db: AsyncSession,
    visit: Visit,
    site_trial_id: UUID | None,
    settings: OrgSettings,
) -> float:
    """Resolve the effective duration for a visit.

    ``site_trial_id`` is optional — pass it to allow a per-site override to
    win; pass ``None`` for trial-level resolution.
    """
    if site_trial_id is not None:
        override = (
            await db.execute(
                select(SiteTrialVisitOverride).where(
                    SiteTrialVisitOverride.site_trial_id == site_trial_id,
                    SiteTrialVisitOverride.visit_id == visit.id,
                )
            )
        ).scalar_one_or_none()
        if override is not None:
            return float(override.duration_hours)

    if visit.duration_hours_override is not None:
        return float(visit.duration_hours_override)

    return _type_default(settings, visit.visit_type)
