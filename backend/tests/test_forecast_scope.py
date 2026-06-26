"""Forecast scope by trial status — the Planned-status feature (PRD §6.9 / §7.1).

A `planned` trial is forecast-ready but reported separately from `active`. These
tests drive the transitions and assert the network forecast / legend honor the
`scope` selector (active / planned / combined), so reporting can split committed
volume from future pipeline volume.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


def _future_monday(weeks_ahead: int = 2) -> date:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(weeks=weeks_ahead)


MONDAY_W0 = _future_monday(weeks_ahead=2)
MONDAY_W2 = MONDAY_W0 + timedelta(weeks=2)


async def _signup_login(client: AsyncClient, name: str) -> dict:
    org = (
        await client.post(
            "/orgs",
            json={
                "org_name": name,
                "default_timezone": "America/New_York",
                "admin_email": f"admin@{name.lower()}.example.com",
                "admin_password": "correct-horse-battery-staple",
                "admin_name": f"{name} admin",
            },
        )
    ).json()
    res = await client.post(
        "/auth/login",
        json={
            "email": f"admin@{name.lower()}.example.com",
            "password": "correct-horse-battery-staple",
            "org_id": org["id"],
        },
    )
    assert res.status_code == 204
    return org


async def _seed_full_trial(client: AsyncClient, org_name: str) -> dict:
    """Create a fully forecast-ready trial (SoA + site + curve + one enrollment
    week), left in *draft*. Returns the identifiers."""
    org = await _signup_login(client, org_name)
    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Zero", "total_dropout_pct": 0.0}
        )
    ).json()
    site = (
        await client.post(
            "/sites",
            json={
                "name": "Scope Site",
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
                "name": "Scope Trial",
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
    for v in (
        {"name": "v0", "visit_type": "randomization", "target_day_offset": 0, "sort_order": 0},
        {"name": "v1", "visit_type": "follow_up", "target_day_offset": 7, "sort_order": 1},
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
    return {"org_id": org["id"], "site_id": site["id"], "trial_id": trial["id"]}


def _network(client: AsyncClient, scope: str | None = None):
    params = {"from": MONDAY_W0.isoformat(), "to": MONDAY_W2.isoformat()}
    if scope is not None:
        params["scope"] = scope
    return client.get("/forecast/network", params=params)


async def test_plan_transition_sets_status(client: AsyncClient) -> None:
    ids = await _seed_full_trial(client, "PlanOrg")
    res = await client.post(f"/trials/{ids['trial_id']}/plan")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "planned"


async def test_planned_trial_excluded_from_active_scope_included_in_planned_and_combined(
    client: AsyncClient,
) -> None:
    ids = await _seed_full_trial(client, "ScopeOrg")
    await client.post(f"/trials/{ids['trial_id']}/plan")

    # Default scope is active-only → a planned trial contributes nothing.
    assert len((await _network(client)).json()) == 0
    assert len((await _network(client, "active")).json()) == 0
    # Planned and combined scopes include it.
    assert len((await _network(client, "planned")).json()) == 3
    assert len((await _network(client, "combined")).json()) == 3


async def test_active_trial_excluded_from_planned_scope(client: AsyncClient) -> None:
    ids = await _seed_full_trial(client, "ActiveScopeOrg")
    res = await client.post(f"/trials/{ids['trial_id']}/activate")
    assert res.status_code == 200, res.text

    assert len((await _network(client, "active")).json()) == 3
    assert len((await _network(client, "planned")).json()) == 0
    assert len((await _network(client, "combined")).json()) == 3


async def test_legend_is_scope_aware(client: AsyncClient) -> None:
    ids = await _seed_full_trial(client, "LegendOrg")
    await client.post(f"/trials/{ids['trial_id']}/plan")

    assert (await client.get("/active-trials")).json() == []
    assert (await client.get("/active-trials", params={"scope": "active"})).json() == []
    planned = (await client.get("/active-trials", params={"scope": "planned"})).json()
    assert [t["id"] for t in planned] == [ids["trial_id"]]
    combined = (await client.get("/active-trials", params={"scope": "combined"})).json()
    assert [t["id"] for t in combined] == [ids["trial_id"]]


async def test_activate_from_planned(client: AsyncClient) -> None:
    ids = await _seed_full_trial(client, "PromoteOrg")
    assert (await client.post(f"/trials/{ids['trial_id']}/plan")).status_code == 200
    res = await client.post(f"/trials/{ids['trial_id']}/activate")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"
    assert len((await _network(client, "active")).json()) == 3


async def test_plan_requires_forecast_readiness(client: AsyncClient) -> None:
    """A bare draft (no SoA, no site) cannot be marked planned — same gate as
    activation."""
    await _signup_login(client, "BareOrg")
    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Zero", "total_dropout_pct": 0.0}
        )
    ).json()
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "Bare Trial",
                "fpfv": "2025-01-06",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
                "enrollment_target": 100,
                "screening_target": 125,
                "attrition_curve_id": curve["id"],
            },
        )
    ).json()
    res = await client.post(f"/trials/{trial['id']}/plan")
    assert res.status_code == 422, res.text
    reasons = {f["reason"] for f in res.json()["detail"]["failures"]}
    assert "no_visits" in reasons
    assert "no_sites" in reasons


async def test_delete_blocked_while_planned(client: AsyncClient) -> None:
    ids = await _seed_full_trial(client, "DeleteGuardOrg")
    await client.post(f"/trials/{ids['trial_id']}/plan")
    res = await client.request("DELETE", f"/trials/{ids['trial_id']}")
    assert res.status_code == 409, res.text
    assert "planned" in res.json()["detail"]


async def test_trials_readiness_reports_missing_requirements(
    client: AsyncClient,
) -> None:
    """GET /trials/readiness reuses the activation gate: a fully-configured
    draft is ready; a bare draft lists what's missing."""
    ids = await _seed_full_trial(client, "ReadyOrg")  # complete draft

    # A bare trial: attrition curve only, no SoA / no site.
    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Zero", "total_dropout_pct": 0.0}
        )
    ).json()
    bare = (
        await client.post(
            "/trials",
            json={
                "name": "Bare",
                "fpfv": "2025-01-06",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
                "enrollment_target": 100,
                "screening_target": 125,
                "attrition_curve_id": curve["id"],
            },
        )
    ).json()

    by_trial = {
        e["trial_id"]: e for e in (await client.get("/trials/readiness")).json()
    }
    assert by_trial[ids["trial_id"]]["ready"] is True
    assert by_trial[ids["trial_id"]]["failures"] == []

    bare_entry = by_trial[bare["id"]]
    assert bare_entry["ready"] is False
    reasons = {f["reason"] for f in bare_entry["failures"]}
    assert "no_visits" in reasons
    assert "no_sites" in reasons
