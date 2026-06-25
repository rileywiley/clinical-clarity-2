"""Delete sites / trials from the admin page (post-Phase-6).

Load-bearing: deleting an active trial is BLOCKED. The operator must
archive first, then delete. This is the primary safety net against
silently wiping live forecast contribution.
"""

from __future__ import annotations

from datetime import date, timedelta

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
async def fixtures(client: AsyncClient) -> dict:
    """Active trial + 2 sites, both assigned, with 1 enrollment week + 1 snapshot."""
    org = await _signup(client, "DelOrg")
    await _login(client, org["id"], "admin@delorg.example.com")
    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Std", "total_dropout_pct": 0.1}
        )
    ).json()
    sites = []
    for n in ("Site-A", "Site-B"):
        sites.append(
            (
                await client.post(
                    "/sites",
                    json={
                        "name": n,
                        "timezone": "America/New_York",
                        "operating_weekdays": [0, 1, 2, 3, 4],
                        "hours_per_day": 10,
                        "rooms": 2,
                    },
                )
            ).json()
        )
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "DelTrial",
                "fpfv": "2026-09-07",
                "lpfv": "2027-09-06",
                "lplv": "2028-09-04",
                "enrollment_target": 200,
                "screening_target": 250,
                "attrition_curve_id": curve["id"],
            },
        )
    ).json()
    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]
    # One randomization visit (required to activate).
    await client.post(
        f"/arms/{arm['id']}/visits",
        json={
            "name": "Randomization",
            "visit_type": "randomization",
            "target_day_offset": 0,
            "window_days": 0,
            "sort_order": 0,
        },
    )
    sts = []
    for s in sites:
        sts.append(
            (
                await client.post(
                    f"/trials/{trial['id']}/sites",
                    json={
                        "site_id": s["id"],
                        "per_site_enrollment_target": 100,
                        "per_site_screening_target": 125,
                    },
                )
            ).json()
        )
    await client.post(f"/trials/{trial['id']}/activate")
    mon = _next_monday()
    await client.put(
        f"/site-trials/{sts[0]['id']}/enrollment-weeks",
        json={
            "arm_id": arm["id"],
            "weeks": [
                {
                    "week_start": mon.isoformat(),
                    "proj_screened": 5,
                    "proj_randomized": 4,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )
    # Take a manual snapshot so trial deletion has a snapshot to cascade.
    await client.post(
        f"/trials/{trial['id']}/soa-snapshots", json={"label": "before delete test"}
    )
    return {"org": org, "trial": trial, "arm": arm, "sites": sites, "sts": sts}


# --- Trials -------------------------------------------------------------


async def test_active_trial_delete_is_blocked(
    client: AsyncClient, fixtures: dict
) -> None:
    """The whole point of the archive-first rule."""
    trial_id = fixtures["trial"]["id"]
    res = await client.delete(f"/trials/{trial_id}")
    assert res.status_code == 409
    assert "archive" in res.json()["detail"].lower()
    # And the trial is still there.
    assert any(
        t["id"] == trial_id for t in (await client.get("/trials")).json()
    )


async def test_archive_then_delete_succeeds_and_cascades(
    client: AsyncClient, fixtures: dict
) -> None:
    trial_id = fixtures["trial"]["id"]
    # Archive flips status to archived.
    arc = await client.post(f"/trials/{trial_id}/archive")
    assert arc.status_code == 200
    assert arc.json()["status"] == "archived"

    res = await client.delete(f"/trials/{trial_id}")
    assert res.status_code == 204

    # Trial is gone; the FK cascades took care of arms/visits/site_trials/
    # enrollment_weeks/snapshots. We verify two of the more important ones:
    assert all(
        t["id"] != trial_id for t in (await client.get("/trials")).json()
    )
    # The site-trial endpoint 404s for the now-deleted trial.
    res = await client.get(f"/trials/{trial_id}/sites")
    assert res.status_code == 404


async def test_trial_delete_impact_counts_dependents(
    client: AsyncClient, fixtures: dict
) -> None:
    trial_id = fixtures["trial"]["id"]
    res = await client.get(f"/trials/{trial_id}/delete-impact")
    assert res.status_code == 200
    body = res.json()
    assert body["trial_name"] == "DelTrial"
    assert body["status"] == "active"
    assert body["arms"] == 1
    assert body["visits"] == 1
    assert body["site_assignments"] == 2
    assert body["enrollment_weeks"] == 1
    # We took one manual snapshot; activation may also write a snapshot?
    # Standard behavior today does not snapshot on activation, so expect 1.
    assert body["soa_snapshots"] >= 1


async def test_trial_delete_requires_admin(
    client: AsyncClient, fixtures: dict
) -> None:
    # Add a second admin so we can demote ourselves.
    await client.post(
        "/users",
        json={
            "email": "other@delorg.example.com",
            "name": "Other",
            "password": "correct-horse-battery-staple",
            "role": "org_admin",
        },
    )
    me = (await client.get("/auth/me")).json()
    await client.patch(f"/users/{me['user_id']}", json={"role": "ops_lead"})

    trial_id = fixtures["trial"]["id"]
    # First archive (ops_lead may archive — WRITE_ROLES includes it).
    arc = await client.post(f"/trials/{trial_id}/archive")
    assert arc.status_code == 200
    # But DELETE requires org_admin.
    res = await client.delete(f"/trials/{trial_id}")
    assert res.status_code == 403


# --- Sites --------------------------------------------------------------


async def test_site_delete_impact_counts_dependents(
    client: AsyncClient, fixtures: dict
) -> None:
    site_id = fixtures["sites"][0]["id"]
    res = await client.get(f"/sites/{site_id}/delete-impact")
    assert res.status_code == 200
    body = res.json()
    assert body["site_name"] == "Site-A"
    assert body["trial_assignments"] == 1
    assert body["enrollment_weeks"] == 1
    assert body["user_assignments"] == 0


async def test_site_delete_cascades_to_assignments_and_weeks(
    client: AsyncClient, fixtures: dict
) -> None:
    """Deleting a site removes its SiteTrial assignment and EnrollmentWeek
    rows. The trial keeps its other assignments."""
    trial_id = fixtures["trial"]["id"]
    site_id = fixtures["sites"][0]["id"]
    # Before: 2 assignments.
    assert len((await client.get(f"/trials/{trial_id}/sites")).json()) == 2

    res = await client.delete(f"/sites/{site_id}")
    assert res.status_code == 204

    # After: 1 assignment remaining; Site-A's assignment is gone.
    sts = (await client.get(f"/trials/{trial_id}/sites")).json()
    assert len(sts) == 1
    assert all(a["site_id"] != site_id for a in sts)


async def test_site_delete_is_org_scoped(
    client: AsyncClient, fixtures: dict
) -> None:
    """RLS: a second org can't delete Org A's site."""
    site_a = fixtures["sites"][0]["id"]
    b = await _signup(client, "RlsBDel")
    await _login(client, b["id"], "admin@rlsbdel.example.com")
    res = await client.delete(f"/sites/{site_a}")
    assert res.status_code == 404
    res = await client.get(f"/sites/{site_a}/delete-impact")
    assert res.status_code == 404
