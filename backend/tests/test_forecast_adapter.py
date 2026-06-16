"""Phase 4 gate — DB-fed forecast matches engine golden values exactly.

PRD §9.2 Phase 4 gate: "rendered forecasts match engine golden values for a
seeded dataset." This test persists the equivalent of the engine's
``single_cohort_fan`` golden master into Postgres via the adapter chain,
runs the adapter, and asserts the resulting ForecastCells match values that
were also hand-computed in `engine/tests/test_forecast_golden_masters.py`.

If this passes and the engine golden masters still pass, the wiring layer
is faithful to the math.

**Time-shifting:** the engine fixture uses a fixed anchor Monday (2026-06-01)
as both TODAY and the enrollment week. Once real ``date.today()`` advances
past that anchor, seeding via the API would trip the past-projection lock.
The fixture computes a future Monday at runtime so the seed always succeeds.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from uuid import UUID

import pytest
from engine.forecast import compute_forecast
from engine.types import VisitType
from httpx import AsyncClient

from app.services.forecast_adapter import build_commitments


def _future_monday(weeks_ahead: int = 2) -> date:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(weeks=weeks_ahead)


async def _signup(client: AsyncClient, name: str = "ParityOrg") -> dict:
    res = await client.post(
        "/orgs",
        json={
            "org_name": name,
            "default_timezone": "America/New_York",
            "admin_email": f"admin@{name.lower()}.example.com",
            "admin_password": "correct-horse-battery-staple",
            "admin_name": f"{name} admin",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _login(client: AsyncClient, org_id: str, email: str) -> None:
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery-staple", "org_id": org_id},
    )
    assert res.status_code == 204


# Mirror the engine fixture's relative anchor shape, but shift the absolute
# dates forward so the seed never hits the past-projection lock. The fixture
# `MONDAY_W0` becomes the "anchor week" that we pass as TODAY into the engine.
MONDAY_W0 = _future_monday(weeks_ahead=2)
MONDAY_W1 = MONDAY_W0 + timedelta(weeks=1)
MONDAY_W2 = MONDAY_W0 + timedelta(weeks=2)
TODAY = MONDAY_W0
HORIZON = MONDAY_W0 + timedelta(weeks=16)


@pytest.fixture
async def seeded_org(client: AsyncClient) -> dict:
    """Persist a known commitment via the API and return the identifiers.

    Mirrors the engine's ``test_single_cohort_fan`` fixture: 1 site, 1 trial,
    1 arm, 4 visits, 0% attrition, 10 randomized in W0.
    """
    org = await _signup(client, "ParityOrg")
    await _login(client, org["id"], "admin@parityorg.example.com")

    # The engine uses the org's standard org_duration_defaults
    # (screening=5, randomization=4, follow_up=2, other=3). Signup seeds those.

    # PATCH the attrition curve to 0% for parity with the fixture
    # (signup seeds Low=10/Standard=20/High=35; we need 0%).
    curve = (
        await client.post(
            "/attrition-curves",
            json={"name": "Zero", "total_dropout_pct": 0.0},
        )
    ).json()

    site = (
        await client.post(
            "/sites",
            json={
                "name": "Parity Site",
                "timezone": "America/New_York",
                "operating_weekdays": [0, 1, 2, 3, 4],
                "hours_per_day": 10,
                "rooms": 2,
            },
        )
    ).json()

    trial = (
        await client.post(
            "/trials",
            json={
                "name": "Parity Trial",
                "fpfv": "2025-01-06",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
                "enrollment_target": 100,
                "screening_target": 125,
                "attrition_curve_id": curve["id"],
            },
        )
    ).json()
    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]

    # Visits — same 4 as the engine fixture (sort_order maps to engine's order).
    for v in (
        {"name": "v0", "visit_type": "randomization", "target_day_offset": 0, "sort_order": 0},
        {"name": "v1", "visit_type": "follow_up", "target_day_offset": 7, "sort_order": 1},
        {"name": "v2", "visit_type": "follow_up", "target_day_offset": 14, "sort_order": 2},
        {"name": "v3", "visit_type": "other", "target_day_offset": 28, "sort_order": 3},
    ):
        res = await client.post(f"/arms/{arm['id']}/visits", json=v)
        assert res.status_code == 201, res.text

    site_trial = (
        await client.post(
            f"/trials/{trial['id']}/sites",
            json={
                "site_id": site["id"],
                "per_site_enrollment_target": 100,
                "per_site_screening_target": 125,
            },
        )
    ).json()

    # Activate so build_commitments(active_only=True) picks it up.
    res = await client.post(f"/trials/{trial['id']}/activate")
    assert res.status_code == 200, res.text

    # Seed the one EnrollmentWeek: 10 randomized in W0.
    res = await client.put(
        f"/site-trials/{site_trial['id']}/enrollment-weeks",
        json={
            "arm_id": arm["id"],
            "weeks": [
                {
                    "week_start": MONDAY_W0.isoformat(),
                    "proj_screened": 0,
                    "proj_randomized": 10,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )
    assert res.status_code == 200, res.text

    return {
        "org_id": org["id"],
        "site_id": site["id"],
        "trial_id": trial["id"],
        "arm_id": arm["id"],
        "site_trial_id": site_trial["id"],
    }


async def test_db_fed_forecast_matches_engine_golden_values(
    client: AsyncClient, seeded_org: dict
) -> None:
    """The Phase 4 load-bearing assertion: persisted data → adapter → engine
    produces the same ForecastCells as the engine fixture.

    From engine.tests.test_forecast_golden_masters.test_single_cohort_fan:
        W0: 10 randomization-type visits, demand_hours = 10 * 4 = 40
        W1: 10 follow_up,                 demand_hours = 10 * 2 = 20
        W2: 10 follow_up,                 demand_hours = 10 * 2 = 20
        Capacity = 2 rooms * 5 days * 10 hours = 100 hr/week
        Utilization: W0 = 0.40, W1/W2 = 0.20
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings
    from app.db import set_tenant

    engine_db = create_async_engine(get_settings().database_url_admin)
    sm = async_sessionmaker(engine_db, expire_on_commit=False)
    org_uuid = UUID(seeded_org["org_id"])
    site_uuid = UUID(seeded_org["site_id"])

    async with sm() as session:
        # app_owner is BYPASSRLS but we still set tenant so the read paths
        # behave identically to the runtime path.
        await set_tenant(session, org_uuid)
        commitments = await build_commitments(session, org_uuid)
    await engine_db.dispose()

    # We seeded exactly one commitment (one site × one trial × one arm).
    assert len(commitments) == 1
    c = commitments[0]
    assert c.site.id == seeded_org["site_id"]

    out = compute_forecast(commitments, TODAY, HORIZON)
    cells = {wk: cell for (sid, wk), cell in out.items() if sid == str(site_uuid)}

    # W0: 10 randomization visits, 40 demand hours, 100 capacity, util 0.40.
    assert math.isclose(cells[MONDAY_W0].visits_by_type[VisitType.RANDOMIZATION], 10.0)
    assert math.isclose(cells[MONDAY_W0].demand_hours, 40.0)
    assert math.isclose(cells[MONDAY_W0].capacity_hours, 100.0)
    assert math.isclose(cells[MONDAY_W0].utilization, 0.40)

    # W1 + W2: 10 follow_up visits each, 20 demand hours, util 0.20.
    assert math.isclose(cells[MONDAY_W1].visits_by_type[VisitType.FOLLOW_UP], 10.0)
    assert math.isclose(cells[MONDAY_W1].demand_hours, 20.0)
    assert math.isclose(cells[MONDAY_W1].utilization, 0.20)

    assert math.isclose(cells[MONDAY_W2].visits_by_type[VisitType.FOLLOW_UP], 10.0)
    assert math.isclose(cells[MONDAY_W2].utilization, 0.20)


async def test_network_forecast_endpoint_returns_cells(
    client: AsyncClient, seeded_org: dict
) -> None:
    res = await client.get(
        "/forecast/network",
        params={"from": MONDAY_W0.isoformat(), "to": MONDAY_W2.isoformat()},
    )
    assert res.status_code == 200, res.text
    cells = res.json()
    # 3 weeks × 1 site
    assert len(cells) == 3
    # Each cell has a utilization ≥ 0 (or null).
    for c in cells:
        assert c["site_id"] == seeded_org["site_id"]
        assert c["capacity_hours"] == 100.0


async def test_site_forecast_endpoint_scoped(
    client: AsyncClient, seeded_org: dict
) -> None:
    site_id = seeded_org["site_id"]
    res = await client.get(
        f"/sites/{site_id}/forecast",
        params={"from": MONDAY_W0.isoformat(), "to": MONDAY_W2.isoformat()},
    )
    assert res.status_code == 200, res.text
    cells = res.json()
    assert len(cells) == 3
    assert all(c["site_id"] == site_id for c in cells)


async def test_trial_metrics_endpoint(
    client: AsyncClient, seeded_org: dict
) -> None:
    trial_id = seeded_org["trial_id"]
    res = await client.get(
        f"/trials/{trial_id}/metrics",
        params={
            "window_start": (MONDAY_W0).isoformat(),
            "window_end": (MONDAY_W2).isoformat(),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["trial_id"] == trial_id
    assert body["randomization_target"] == 100
    assert body["screening_target"] == 125
    # Window has the 1 seeded week with 10 randomized, 0 screened.
    assert body["metrics"]["randomized"] == 10


async def test_calendar_endpoint(client: AsyncClient, seeded_org: dict) -> None:
    """Asserts the month containing MONDAY_W0 has a randomization peak on
    that Monday and zero capacity on weekend days."""
    import calendar as _cal

    site_id = seeded_org["site_id"]
    month_str = f"{MONDAY_W0.year:04d}-{MONDAY_W0.month:02d}"
    res = await client.get(
        f"/sites/{site_id}/forecast/calendar",
        params={"month": month_str},
    )
    assert res.status_code == 200, res.text
    days = res.json()
    expected_n = _cal.monthrange(MONDAY_W0.year, MONDAY_W0.month)[1]
    assert len(days) == expected_n

    # The Monday that anchors W0 — randomization visit lands here.
    anchor = next(d for d in days if d["day"] == MONDAY_W0.isoformat())
    assert anchor["visits_by_type"].get("randomization", 0) == 10
    assert anchor["capacity_hours"] == 20.0  # 2 rooms * 10 hrs/day

    # The Saturday after that Monday — non-operating.
    sat = MONDAY_W0 + timedelta(days=5)
    if sat.month == MONDAY_W0.month:  # may have crossed month boundary
        sat_cell = next(d for d in days if d["day"] == sat.isoformat())
        assert sat_cell["capacity_hours"] == 0.0
        assert sat_cell["utilization"] is None


async def test_forecast_rls_blocks_cross_org(client: AsyncClient) -> None:
    """Org B can't see Org A's forecast or metrics endpoints."""
    org_a = await _signup(client, "RlsA")
    await _login(client, org_a["id"], "admin@rlsa.example.com")
    site_a = (
        await client.post(
            "/sites", json={"name": "A", "timezone": "UTC"}
        )
    ).json()

    # Org B
    org_b = await _signup(client, "RlsB")
    await _login(client, org_b["id"], "admin@rlsb.example.com")

    # B can't see A's site forecast.
    res = await client.get(f"/sites/{site_a['id']}/forecast")
    assert res.status_code == 404
    # B's own /forecast/network returns empty (no commitments).
    res = await client.get("/forecast/network")
    assert res.status_code == 200
    assert res.json() == []
