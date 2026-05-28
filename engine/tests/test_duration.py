"""Unit tests for duration resolution (PRD §5.2 order)."""

from __future__ import annotations

from engine.duration import effective_duration
from engine.types import OrgDurationDefaults, SiteTrialVisitOverride, VisitType
from tests._builders import visit

DEFAULTS = OrgDurationDefaults(
    screening=5.0, randomization=4.0, follow_up=2.0, other=3.0
)


def test_uses_org_default_when_no_overrides() -> None:
    v = visit("v1", VisitType.FOLLOW_UP, 14)
    assert effective_duration(v, DEFAULTS, ()) == 2.0


def test_visit_level_override_wins_over_default() -> None:
    v = visit("v1", VisitType.FOLLOW_UP, 14, duration_hours_override=2.5)
    assert effective_duration(v, DEFAULTS, ()) == 2.5


def test_site_override_wins_over_visit_override() -> None:
    v = visit("v1", VisitType.FOLLOW_UP, 14, duration_hours_override=2.5)
    overrides = (SiteTrialVisitOverride(visit_id="v1", duration_hours=3.0),)
    assert effective_duration(v, DEFAULTS, overrides) == 3.0


def test_unrelated_site_override_does_not_apply() -> None:
    v = visit("v1", VisitType.FOLLOW_UP, 14)
    overrides = (SiteTrialVisitOverride(visit_id="other", duration_hours=99.0),)
    assert effective_duration(v, DEFAULTS, overrides) == 2.0  # org default
