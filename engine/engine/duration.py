"""Effective-duration resolution per PRD §5.2.

Resolution order for a visit's effective duration (first non-null wins):
1. site-trial visit override (per-site duration for this specific visit)
2. visit-level override (``Visit.duration_hours_override``)
3. org-level type default (``OrgDurationDefaults`` keyed by visit_type)

The engine receives all three layers as inputs — it doesn't read OrgSettings
or the database. The backend resolves and passes them in. This keeps the engine
pure (CLAUDE.md golden rule #2) while still honoring "defaults resolve live"
(PRD §5.2): the backend re-fetches OrgSettings on each forecast run.
"""

from __future__ import annotations

from collections.abc import Iterable

from engine.types import (
    OrgDurationDefaults,
    SiteTrialVisitOverride,
    Visit,
    VisitType,
)


def _type_default(defaults: OrgDurationDefaults, vt: VisitType) -> float:
    match vt:
        case VisitType.SCREENING:
            return defaults.screening
        case VisitType.RANDOMIZATION:
            return defaults.randomization
        case VisitType.FOLLOW_UP:
            return defaults.follow_up
        case VisitType.OTHER:
            return defaults.other


def effective_duration(
    visit: Visit,
    defaults: OrgDurationDefaults,
    site_overrides: Iterable[SiteTrialVisitOverride] = (),
) -> float:
    """Resolve the visit's effective duration in hours."""
    for o in site_overrides:
        if o.visit_id == visit.id:
            return o.duration_hours
    if visit.duration_hours_override is not None:
        return visit.duration_hours_override
    return _type_default(defaults, visit.visit_type)
