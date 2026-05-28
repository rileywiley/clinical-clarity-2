"""Trial draft→active validator.

Encodes the rule documented in saved project memory (see
project-trial-activation-rule):

1. SoA present: ≥1 visit total *and* ≥1 visit of `visit_type = randomization`
   across the trial's arms.
2. ≥1 SiteTrial assignment.
3. AttritionCurve assigned (`trial.attrition_curve_id is not None`).

Pricing is **not** part of activation — PRD §7.1 separates "volume-ready"
from "revenue-ready."

On failure, returns a list of structured reasons so the API can surface them
together rather than fail-fast one at a time (better UX in the wizard).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site_trial import SiteTrial
from app.models.trial import Arm, Trial
from app.models.visit import Visit, VisitType


@dataclass(frozen=True, slots=True)
class ActivationFailure:
    reason: str
    detail: str


async def validate_can_activate(db: AsyncSession, trial: Trial) -> list[ActivationFailure]:
    """Return an empty list on success; otherwise a list of failure reasons."""
    failures: list[ActivationFailure] = []

    # --- 1. SoA present ----------------------------------------------------
    arm_ids = (
        await db.execute(select(Arm.id).where(Arm.trial_id == trial.id))
    ).scalars().all()
    if not arm_ids:
        failures.append(
            ActivationFailure(
                "no_arms",
                "Trial has no arms. Single-arm trials should get a Default Arm at creation.",
            )
        )
    else:
        visits = (
            await db.execute(select(Visit).where(Visit.arm_id.in_(arm_ids)))
        ).scalars().all()
        if not visits:
            failures.append(
                ActivationFailure(
                    "no_visits",
                    "Trial has no Schedule-of-Activities visits.",
                )
            )
        elif not any(v.visit_type is VisitType.RANDOMIZATION for v in visits):
            failures.append(
                ActivationFailure(
                    "no_randomization_visit",
                    "SoA needs at least one visit of type 'randomization' (the anchor day).",
                )
            )

    # --- 2. ≥1 site assigned ----------------------------------------------
    sites_count = (
        await db.execute(
            select(SiteTrial.id).where(SiteTrial.trial_id == trial.id, SiteTrial.active.is_(True))
        )
    ).scalars().all()
    if not sites_count:
        failures.append(
            ActivationFailure(
                "no_sites",
                "Trial has no active SiteTrial assignments.",
            )
        )

    # --- 3. Attrition curve assigned --------------------------------------
    if trial.attrition_curve_id is None:
        failures.append(
            ActivationFailure(
                "no_attrition_curve",
                "Trial has no attrition curve assigned.",
            )
        )

    return failures
