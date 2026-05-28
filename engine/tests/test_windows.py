"""Unit tests for triangular smearing — every value hand-computed."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from engine.windows import smear_count, triangular_weights


def test_zero_window_is_point_mass() -> None:
    d = date(2026, 6, 3)
    w = triangular_weights(d, 0)
    assert w == {d: 1.0}


def test_window_two_matches_hand_computation() -> None:
    """W=2 → raw weights (1,2,3,2,1) / 9 = (1/9, 2/9, 3/9, 2/9, 1/9)."""
    d = date(2026, 6, 3)
    w = triangular_weights(d, 2)
    assert math.isclose(w[d - timedelta(days=2)], 1 / 9)
    assert math.isclose(w[d - timedelta(days=1)], 2 / 9)
    assert math.isclose(w[d], 3 / 9)
    assert math.isclose(w[d + timedelta(days=1)], 2 / 9)
    assert math.isclose(w[d + timedelta(days=2)], 1 / 9)
    assert math.isclose(sum(w.values()), 1.0)


def test_window_seven_sums_to_one() -> None:
    """W=7 → 15 days, raw weights (1..8..1), sum (W+1)² = 64."""
    d = date(2026, 6, 3)
    w = triangular_weights(d, 7)
    assert len(w) == 15
    assert math.isclose(sum(w.values()), 1.0)
    assert math.isclose(w[d], 8 / 64)  # peak


def test_negative_window_rejected() -> None:
    with pytest.raises(ValueError):
        triangular_weights(date(2026, 6, 3), -1)


def test_smear_count_multiplies_uniformly() -> None:
    d = date(2026, 6, 3)
    out = smear_count(d, 2, 100.0)
    # peak should be 100 * 3/9 = 33.333...
    assert math.isclose(out[d], 100 * 3 / 9)
    assert math.isclose(sum(out.values()), 100.0)
