"""Unit tests for attrition — linear back-loaded, hand-computed."""

from __future__ import annotations

import math

from engine.attrition import survival_by_visit
from engine.types import VisitType
from tests._builders import attrition, visit


def test_screening_visits_always_survive_fully() -> None:
    visits = (
        visit("s1", VisitType.SCREENING, -28, sort_order=0),
        visit("s2", VisitType.SCREENING, -14, sort_order=1),
        visit("r", VisitType.RANDOMIZATION, 0, sort_order=2),
    )
    surv = survival_by_visit(visits, attrition(0.20))
    assert surv["s1"] == 1.0
    assert surv["s2"] == 1.0


def test_linear_decay_across_randomized_chain() -> None:
    """5 randomized-chain visits, 20% total dropout → survival at indices
    0..4 = 1.0, 0.95, 0.90, 0.85, 0.80."""
    visits = (
        visit("r", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 7, sort_order=1),
        visit("v2", VisitType.FOLLOW_UP, 28, sort_order=2),
        visit("v3", VisitType.FOLLOW_UP, 56, sort_order=3),
        visit("v4", VisitType.OTHER, 84, sort_order=4),
    )
    surv = survival_by_visit(visits, attrition(0.20))
    assert math.isclose(surv["r"], 1.0)
    assert math.isclose(surv["v1"], 0.95)
    assert math.isclose(surv["v2"], 0.90)
    assert math.isclose(surv["v3"], 0.85)
    assert math.isclose(surv["v4"], 0.80)


def test_high_attrition_preset() -> None:
    """3 randomized visits, 35% total → 1.0, 0.825, 0.65."""
    visits = (
        visit("r", VisitType.RANDOMIZATION, 0, sort_order=0),
        visit("v1", VisitType.FOLLOW_UP, 14, sort_order=1),
        visit("v2", VisitType.FOLLOW_UP, 28, sort_order=2),
    )
    surv = survival_by_visit(visits, attrition(0.35))
    assert math.isclose(surv["r"], 1.0)
    assert math.isclose(surv["v1"], 0.825)
    assert math.isclose(surv["v2"], 0.65)


def test_single_visit_chain_applies_full_dropout() -> None:
    visits = (visit("r", VisitType.RANDOMIZATION, 0, sort_order=0),)
    surv = survival_by_visit(visits, attrition(0.20))
    assert math.isclose(surv["r"], 0.80)


def test_screening_only_chain_no_randomized() -> None:
    visits = (visit("s1", VisitType.SCREENING, -14, sort_order=0),)
    surv = survival_by_visit(visits, attrition(0.20))
    assert surv == {"s1": 1.0}
