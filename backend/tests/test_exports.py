"""Phase 6 — CSV export endpoints.

Exercises shape + headers + RLS. We don't re-test the engine's math here —
the forecast adapter parity test (test_forecast_adapter.py) already locks that
down. This test confirms CSV serialization is correct and the endpoint plumbing
hands the right cells to the formatter.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.models.soa_parse_job import SoaParseJob  # noqa: F401 — register table


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


async def _signup(client: AsyncClient, name: str) -> dict:
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
    assert res.status_code == 201
    return res.json()


async def _login(client: AsyncClient, org_id: str, email: str) -> None:
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery-staple", "org_id": org_id},
    )
    assert res.status_code == 204


@pytest.fixture
async def seeded_trial(client: AsyncClient) -> dict:
    """Active trial w/ one assigned site + one randomization visit + one
    enrollment week. Enough for the engine to produce non-empty cells."""
    org = await _signup(client, "P6CsvOrg")
    await _login(client, org["id"], "admin@p6csvorg.example.com")

    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Zero", "total_dropout_pct": 0.0}
        )
    ).json()
    site = (
        await client.post(
            "/sites",
            json={
                "name": "P6 Site",
                "timezone": "America/New_York",
                "operating_weekdays": [0, 1, 2, 3, 4],
                "hours_per_day": 10,
                "rooms": 2,
            },
        )
    ).json()
    next_mon = _next_monday()
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "CSV Trial",
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
    await client.post(
        f"/arms/{arm['id']}/visits",
        json={
            "name": "Randomization",
            "visit_type": "randomization",
            "target_day_offset": 0,
            "price": 500,
            "sort_order": 0,
        },
    )
    st = (
        await client.post(
            f"/trials/{trial['id']}/sites",
            json={
                "site_id": site["id"],
                "per_site_enrollment_target": 100,
                "per_site_screening_target": 125,
            },
        )
    ).json()
    await client.post(f"/trials/{trial['id']}/activate")
    await client.put(
        f"/site-trials/{st['id']}/enrollment-weeks",
        json={
            "arm_id": arm["id"],
            "weeks": [
                {
                    "week_start": next_mon.isoformat(),
                    "proj_screened": 0,
                    "proj_randomized": 10,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )
    return {"org_id": org["id"], "site_id": site["id"]}


async def test_network_csv_headers_and_shape(
    client: AsyncClient, seeded_trial: dict
) -> None:
    res = await client.get("/forecast/network.csv")
    assert res.status_code == 200, res.text
    # Headers — load-bearing for browser download UX.
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    assert ".csv" in res.headers["content-disposition"]

    body = res.text.strip().splitlines()
    assert body[0] == (
        "site_id,week_start,screening_visits,randomization_visits,"
        "follow_up_visits,other_visits,demand_hours,capacity_hours,"
        "utilization_pct,revenue_usd"
    )
    # At least one data row (the seeded week)
    assert len(body) >= 2
    data = body[1].split(",")
    assert UUID(data[0]) == UUID(seeded_trial["site_id"])
    # Capacity for the seeded site = 2 rooms * 5 days * 10 hours = 100.0
    assert "100.0" in body[1]


async def test_site_csv_filters_to_site(
    client: AsyncClient, seeded_trial: dict
) -> None:
    site_id = seeded_trial["site_id"]
    res = await client.get(f"/sites/{site_id}/forecast.csv")
    assert res.status_code == 200, res.text
    # Filename includes the site name (URL-safe form).
    assert "P6_Site" in res.headers["content-disposition"]
    # Every data row's site_id matches.
    rows = res.text.strip().splitlines()[1:]
    for row in rows:
        assert row.split(",")[0] == site_id


async def test_csv_rls_blocks_cross_org(
    client: AsyncClient, seeded_trial: dict
) -> None:
    site_a = seeded_trial["site_id"]

    org_b = await _signup(client, "RlsBCsv")
    await _login(client, org_b["id"], "admin@rlsbcsv.example.com")
    # B's network CSV is empty (no commitments).
    res = await client.get("/forecast/network.csv")
    assert res.status_code == 200
    assert res.text.strip().count("\n") == 0  # header only

    # B can't read A's site CSV.
    res = await client.get(f"/sites/{site_a}/forecast.csv")
    assert res.status_code == 404
