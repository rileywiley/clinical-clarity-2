"""Triangular visit-window smearing (PRD §6.2 rule #3).

A visit at ``target_day_offset = T`` with ``window_days = W`` distributes its
expected count across days ``[T-W, T+W]`` using a triangular (tent) distribution:

- weight at day ``T``                = peak
- weight at day ``T ± W``            = 0
- weights are linear between

For the discrete case, the *raw* weight at day ``T + k`` (for ``|k| ≤ W``) is
``W + 1 - |k|``. Summing across all 2W+1 days gives ``(W + 1)²``. So the
normalized weight at day ``T + k`` is::

    weight(k) = (W + 1 - |k|) / (W + 1)²

Properties:
- weight(0) = 1 / (W + 1)         peak, e.g. W=2 → 1/9 → ~0.333
- sum_k weight(k) = 1             exactly

A degenerate W=0 visit gets all its mass on the target day (weight = 1).

**Horizon clipping policy (project decision, not in PRD):** when the window
extends past the forecast horizon (or before "today"), we do *not* renormalize
the in-range weights. Mass that lands outside the reported range is simply
unreported. See [[project-engine-modeling-decisions]] for the rationale: this
is consistent with PRD §6.3's "conservative on screening load" posture — under-
reporting at edges is the safe direction for a don't-oversell tool.
"""

from __future__ import annotations

from datetime import date, timedelta


def triangular_weights(anchor: date, window_days: int) -> dict[date, float]:
    """Return ``{date: weight}`` covering ``[anchor - window_days, anchor + window_days]``.

    Weights sum to 1.0 (modulo floating-point) across the full 2W+1 days.

    Args:
        anchor: The target day for the visit.
        window_days: ± days around the anchor. ``0`` means a point mass on the
            anchor.

    Raises:
        ValueError: if ``window_days < 0``.
    """
    if window_days < 0:
        raise ValueError(f"window_days must be ≥ 0, got {window_days}")

    if window_days == 0:
        return {anchor: 1.0}

    denom = (window_days + 1) ** 2  # sum of (W+1, W, W-1, ..., 1, ..., W-1, W, W+1) = (W+1)²
    weights: dict[date, float] = {}
    for k in range(-window_days, window_days + 1):
        raw = window_days + 1 - abs(k)
        weights[anchor + timedelta(days=k)] = raw / denom
    return weights


def smear_count(
    anchor: date, window_days: int, count: float
) -> dict[date, float]:
    """Convenience: multiply each triangular weight by ``count``.

    Returns ``{date: count * weight}``. Use this directly when smearing a
    cohort's expected count into the daily grid.
    """
    return {day: count * w for day, w in triangular_weights(anchor, window_days).items()}
