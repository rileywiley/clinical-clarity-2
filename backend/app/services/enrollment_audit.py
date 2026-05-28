"""Append-only audit trail for projection edits (PRD §5.1, §7.3).

Only `proj_screened` and `proj_randomized` are audited. Actuals overwrite, they
don't "change a plan" — and the variance comparison is plan-vs-reality, so we
want the plan immutable in history.

One history row per CHANGED field per save. An unchanged save writes nothing.
"""

from __future__ import annotations

from uuid import UUID

from app.models.enrollment_week import EnrollmentWeek, EnrollmentWeekHistory

AUDITED_FIELDS = ("proj_screened", "proj_randomized")


def diff_projection_fields(
    *,
    org_id: UUID,
    changed_by: UUID,
    existing: EnrollmentWeek,
    new_proj_screened: int,
    new_proj_randomized: int,
) -> list[EnrollmentWeekHistory]:
    """Return zero or more history rows for changes between ``existing`` and the
    new values. Caller adds them to the session along with the update.
    """
    rows: list[EnrollmentWeekHistory] = []
    proposed = {
        "proj_screened": new_proj_screened,
        "proj_randomized": new_proj_randomized,
    }
    for field in AUDITED_FIELDS:
        old = getattr(existing, field)
        new = proposed[field]
        if old != new:
            rows.append(
                EnrollmentWeekHistory(
                    org_id=org_id,
                    enrollment_week_id=existing.id,
                    field=field,
                    old_value=old,
                    new_value=new,
                    changed_by=changed_by,
                )
            )
    return rows
