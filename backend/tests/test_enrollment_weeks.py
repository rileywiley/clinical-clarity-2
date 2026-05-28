"""Phase 3 backend gate — EnrollmentWeek CRUD, past-projection lock, audit, variance."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, name: str = "Phase3Org") -> dict:
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


@pytest.fixture
async def trial_with_site(client: AsyncClient) -> dict:
    """Provision a fully-set-up trial with one assigned site and arm. Returns
    the IDs the tests need."""
    org = await _signup(client, "Phase3Org")
    await _login(client, org["id"], "admin@phase3org.example.com")

    site = (
        await client.post(
            "/sites",
            json={"name": "S1", "timezone": "America/New_York", "rooms": 2, "hours_per_day": 10},
        )
    ).json()

    trial = (
        await client.post(
            "/trials",
            json={
                "name": "T1",
                "fpfv": "2025-01-06",  # well in the past so projections are valid range
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
                "enrollment_target": 100,
                "screening_target": 125,
            },
        )
    ).json()

    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]

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

    return {
        "org_id": org["id"],
        "site_id": site["id"],
        "trial_id": trial["id"],
        "arm_id": arm["id"],
        "site_trial_id": st["id"],
    }


def _next_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _today_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


# --- 1. Bulk PUT round-trip ------------------------------------------------


async def test_bulk_put_roundtrip(client: AsyncClient, trial_with_site: dict) -> None:
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]

    # Use three future weeks so no past-lock complications.
    next_mon = _next_monday(date.today())
    weeks = [
        {"week_start": (next_mon + timedelta(weeks=i)).isoformat(),
         "proj_screened": 10 + i,
         "proj_randomized": 8 + i,
         "actual_screened": None,
         "actual_randomized": None}
        for i in range(3)
    ]

    res = await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={"arm_id": arm_id, "weeks": weeks},
    )
    assert res.status_code == 200, res.text
    saved = res.json()
    assert len(saved) == 3

    # GET back the range.
    res = await client.get(
        f"/site-trials/{st_id}/enrollment-weeks",
        params={
            "arm_id": arm_id,
            "from": next_mon.isoformat(),
            "to": (next_mon + timedelta(weeks=2)).isoformat(),
        },
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 3
    assert rows[0]["proj_screened"] == 10
    assert rows[2]["proj_randomized"] == 10


# --- 2. GET with padding ---------------------------------------------------


async def test_get_pads_missing_weeks(client: AsyncClient, trial_with_site: dict) -> None:
    """Asking for a 6-week range with no saved data should return 6 zero rows."""
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]

    next_mon = _next_monday(date.today())
    res = await client.get(
        f"/site-trials/{st_id}/enrollment-weeks",
        params={
            "arm_id": arm_id,
            "from": next_mon.isoformat(),
            "to": (next_mon + timedelta(weeks=5)).isoformat(),
        },
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 6
    for r in rows:
        assert r["proj_screened"] == 0
        assert r["proj_randomized"] == 0
        assert r["actual_screened"] is None


# --- 3. Past projection edit → 409 ----------------------------------------


async def test_past_projection_edit_rejected_with_409(
    client: AsyncClient, trial_with_site: dict
) -> None:
    """The Phase 3 load-bearing assertion: editing a past projection cell
    returns 409 with the offending week_start so the UI can highlight it."""
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]

    past = _today_monday() - timedelta(weeks=2)
    res = await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={
            "arm_id": arm_id,
            "weeks": [
                {
                    "week_start": past.isoformat(),
                    "proj_screened": 20,  # was 0 → counts as an edit
                    "proj_randomized": 15,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "past_projection_locked"
    assert past.isoformat() in detail["offending_week_starts"]


# --- 4. Past actual edit succeeds -----------------------------------------


async def test_past_actual_edit_allowed(client: AsyncClient, trial_with_site: dict) -> None:
    """Actuals are the *point* of editing past weeks — they must succeed."""
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]

    past = _today_monday() - timedelta(weeks=2)
    res = await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={
            "arm_id": arm_id,
            "weeks": [
                {
                    "week_start": past.isoformat(),
                    "proj_screened": 0,  # unchanged
                    "proj_randomized": 0,  # unchanged
                    "actual_screened": 7,
                    "actual_randomized": 5,
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows[0]["actual_screened"] == 7
    assert rows[0]["actual_randomized"] == 5


# --- 5. Audit history records changed projection fields only -------------


async def test_audit_history_records_projection_changes_only(
    client: AsyncClient, trial_with_site: dict
) -> None:
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]
    next_mon = _next_monday(date.today())

    # First save (insert) — no history rows for baseline.
    await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={
            "arm_id": arm_id,
            "weeks": [
                {
                    "week_start": next_mon.isoformat(),
                    "proj_screened": 10,
                    "proj_randomized": 8,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )

    # Edit proj_screened (10→15), leave proj_randomized at 8, set an actual.
    await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={
            "arm_id": arm_id,
            "weeks": [
                {
                    "week_start": next_mon.isoformat(),
                    "proj_screened": 15,
                    "proj_randomized": 8,
                    "actual_screened": 12,
                    "actual_randomized": None,
                }
            ],
        },
    )

    res = await client.get(
        f"/site-trials/{st_id}/enrollment-weeks/history",
        params={"arm_id": arm_id},
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    # Exactly one history row: the proj_screened change. proj_randomized
    # didn't change → no row. actual_screened is never audited.
    assert len(rows) == 1
    assert rows[0]["field"] == "proj_screened"
    assert rows[0]["old_value"] == 10
    assert rows[0]["new_value"] == 15


# --- 6. Variance: warn-and-allow -----------------------------------------


async def test_variance_under_target_does_not_reject(
    client: AsyncClient, trial_with_site: dict
) -> None:
    """Per PRD §7.3 warn-and-allow: under-target site projections are reported,
    not rejected."""
    st_id = trial_with_site["site_trial_id"]
    arm_id = trial_with_site["arm_id"]
    trial_id = trial_with_site["trial_id"]
    next_mon = _next_monday(date.today())

    # Save 3 weeks * (20 screened, 15 randomized) = 60/45 against goals 125/100.
    weeks = [
        {
            "week_start": (next_mon + timedelta(weeks=i)).isoformat(),
            "proj_screened": 20,
            "proj_randomized": 15,
            "actual_screened": None,
            "actual_randomized": None,
        }
        for i in range(3)
    ]
    res = await client.put(
        f"/site-trials/{st_id}/enrollment-weeks",
        json={"arm_id": arm_id, "weeks": weeks},
    )
    assert res.status_code == 200, res.text  # warn-and-allow: NOT rejected

    res = await client.get(f"/trials/{trial_id}/variance")
    assert res.status_code == 200, res.text
    v = res.json()
    assert v["randomization"]["sum_site"] == 45
    assert v["randomization"]["target"] == 100
    assert v["randomization"]["diff"] == -55  # 55 under target
    assert v["screening"]["sum_site"] == 60
    assert v["screening"]["target"] == 125
    assert v["screening"]["diff"] == -65


# --- 7. RLS isolation on enrollment_weeks --------------------------------


async def test_rls_blocks_cross_org_enrollment_reads(client: AsyncClient) -> None:
    # Org A: full setup + a save.
    org_a = await _signup(client, "RLSA")
    await _login(client, org_a["id"], "admin@rlsa.example.com")
    site_a = (await client.post("/sites", json={"name": "A", "timezone": "UTC"})).json()
    trial_a = (
        await client.post(
            "/trials",
            json={
                "name": "A",
                "fpfv": "2025-01-06",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
            },
        )
    ).json()
    arm_a = (await client.get(f"/trials/{trial_a['id']}/arms")).json()[0]
    st_a = (
        await client.post(
            f"/trials/{trial_a['id']}/sites", json={"site_id": site_a["id"]}
        )
    ).json()
    next_mon = _next_monday(date.today())
    await client.put(
        f"/site-trials/{st_a['id']}/enrollment-weeks",
        json={
            "arm_id": arm_a["id"],
            "weeks": [
                {
                    "week_start": next_mon.isoformat(),
                    "proj_screened": 99,
                    "proj_randomized": 88,
                    "actual_screened": None,
                    "actual_randomized": None,
                }
            ],
        },
    )

    # Org B: log in fresh, try to read Org A's site_trial → 404.
    org_b = await _signup(client, "RLSB")
    await _login(client, org_b["id"], "admin@rlsb.example.com")
    res = await client.get(
        f"/site-trials/{st_a['id']}/enrollment-weeks",
        params={
            "arm_id": arm_a["id"],
            "from": next_mon.isoformat(),
            "to": next_mon.isoformat(),
        },
    )
    assert res.status_code == 404
    # And the variance endpoint on A's trial also 404 for B.
    res = await client.get(f"/trials/{trial_a['id']}/variance")
    assert res.status_code == 404
