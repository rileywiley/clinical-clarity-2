"""Survival/attrition over the SoA (PRD §6.2 rule #2).

Screening visits are never subject to attrition — screen failure is captured
entirely in the screened-vs-randomized gap (PRD §6.2 rule #1). Survival applies
only to the randomized chain: randomization, follow-up, other.

**Shape: linear back-loaded by visit index** (project decision, see
[[project-engine-modeling-decisions]]).

Given a randomized chain of N visits (sorted by ``target_day_offset`` then
``sort_order``) and a curve with ``total_dropout_pct = D``:

- The first randomized visit has survival = 1.0 (the randomization visit
  itself — the cohort starts whole).
- The last randomized visit has survival = 1 - D.
- Intermediate visits decay linearly between those two endpoints.

Formally, for randomized-chain index ``i`` in ``0..N-1``::

    survival(i) = 1.0 - D * i / (N - 1)         when N > 1
    survival(0) = 1.0 - D                       when N == 1 (only the rand visit)

The N==1 case is conservative — a single visit can't decay "across" the chain,
so we apply the full dropout at that one visit. In practice every real trial
has follow-ups, so this is an edge case for fixtures.
"""

from __future__ import annotations

from collections.abc import Iterable

from engine.types import AttritionCurve, Visit, VisitType


def _randomized_chain(visits: Iterable[Visit]) -> list[Visit]:
    """Filter to the post-randomization chain, sorted by (target_day_offset, sort_order)."""
    chain = [v for v in visits if v.visit_type is not VisitType.SCREENING]
    return sorted(chain, key=lambda v: (v.target_day_offset, v.sort_order))


def survival_by_visit(
    visits: Iterable[Visit], curve: AttritionCurve
) -> dict[str, float]:
    """Return ``{visit_id: survival}`` for every visit.

    Screening visits map to ``1.0``. The randomized chain decays linearly with
    visit index according to ``curve.total_dropout_pct``.
    """
    visits = list(visits)
    survival: dict[str, float] = {}

    for v in visits:
        if v.visit_type is VisitType.SCREENING:
            survival[v.id] = 1.0

    chain = _randomized_chain(visits)
    n = len(chain)
    d = curve.total_dropout_pct

    if n == 0:
        return survival
    if n == 1:
        survival[chain[0].id] = 1.0 - d
        return survival

    for i, v in enumerate(chain):
        survival[v.id] = 1.0 - d * i / (n - 1)
    return survival
