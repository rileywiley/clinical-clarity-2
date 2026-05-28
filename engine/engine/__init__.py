"""Forecast engine — pure Python.

CLAUDE.md golden rule #2: this package must remain free of web/DB/HTTP/ORM/framework
imports. It takes data in (see ``engine.types``) and returns results.

Public surface:
- ``compute_forecast(commitments, today, horizon_end)`` from ``engine.forecast``
- ``compute_metrics_row(weeks, ...)`` from ``engine.metrics``
- All input/output types from ``engine.types``
"""

from engine.types import (
    Arm,
    AttritionCurve,
    Commitment,
    EnrollmentWeek,
    ForecastCell,
    MetricsRow,
    OrgDurationDefaults,
    Site,
    SiteTrialVisitOverride,
    Trial,
    Visit,
    VisitType,
    WeekRange,
)

__version__ = "0.1.0"

__all__ = [
    "Arm",
    "AttritionCurve",
    "Commitment",
    "EnrollmentWeek",
    "ForecastCell",
    "MetricsRow",
    "OrgDurationDefaults",
    "Site",
    "SiteTrialVisitOverride",
    "Trial",
    "Visit",
    "VisitType",
    "WeekRange",
    "__version__",
]
