"""CSV export formatter (PRD §7.4).

Pure formatting — takes a list of engine ``ForecastCell`` outputs and yields
CSV lines. Lives in services/ so it stays callable from any router or job
without re-implementing the column layout.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from engine.types import ForecastCell, VisitType

COLUMNS = [
    "site_id",
    "week_start",
    "screening_visits",
    "randomization_visits",
    "follow_up_visits",
    "other_visits",
    "demand_hours",
    "capacity_hours",
    "utilization_pct",
    "revenue_usd",
]


def cells_to_csv(cells: Iterable[ForecastCell]) -> str:
    """Render a list of ForecastCells as a single CSV string.

    Ordering: site_id, then week_start ascending. We sort here so the output
    is deterministic regardless of dict iteration order.
    """
    sorted_cells = sorted(cells, key=lambda c: (c.site_id, c.week_start))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for c in sorted_cells:
        writer.writerow(
            [
                c.site_id,
                c.week_start.isoformat(),
                _round(c.visits_by_type.get(VisitType.SCREENING, 0.0)),
                _round(c.visits_by_type.get(VisitType.RANDOMIZATION, 0.0)),
                _round(c.visits_by_type.get(VisitType.FOLLOW_UP, 0.0)),
                _round(c.visits_by_type.get(VisitType.OTHER, 0.0)),
                _round(c.demand_hours),
                _round(c.capacity_hours),
                f"{c.utilization * 100:.1f}" if c.utilization is not None else "",
                _round(c.revenue),
            ]
        )
    return buf.getvalue()


def _round(v: float) -> str:
    """One decimal place — engine returns floats but downstream tooling
    (Excel, Sheets) reads cleaner numbers without 14-digit noise."""
    return f"{v:.1f}"
