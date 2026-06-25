"""SoA snapshots (post-Phase-6)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.soa_parse_job import SoaParseJob  # noqa: F401 — register table


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
async def trial_with_soa(client: AsyncClient) -> dict:
    """Draft trial with a Default Arm and 3 hand-entered visits."""
    org = await _signup(client, "SnapOrg")
    await _login(client, org["id"], "admin@snaporg.example.com")
    curve = (
        await client.post(
            "/attrition-curves", json={"name": "Z", "total_dropout_pct": 0.0}
        )
    ).json()
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "SnapTrial",
                "fpfv": "2026-09-07",
                "lpfv": "2027-09-06",
                "lplv": "2028-09-04",
                "enrollment_target": 10,
                "screening_target": 12,
                "attrition_curve_id": curve["id"],
            },
        )
    ).json()
    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]
    for name, vt, off in (
        ("Screening", "screening", -14),
        ("Randomization", "randomization", 0),
        ("Week 4", "follow_up", 28),
    ):
        await client.post(
            f"/arms/{arm['id']}/visits",
            json={
                "name": name,
                "visit_type": vt,
                "target_day_offset": off,
                "window_days": 3,
                "sort_order": 0,
            },
        )
    return {"org": org, "trial": trial, "arm": arm}


async def test_manual_snapshot_captures_current_soa(
    client: AsyncClient, trial_with_soa: dict
) -> None:
    trial_id = trial_with_soa["trial"]["id"]
    res = await client.post(
        f"/trials/{trial_id}/soa-snapshots", json={"label": "before edits"}
    )
    assert res.status_code == 201, res.text
    snap = res.json()
    assert snap["reason"] == "manual"
    assert snap["label"] == "before edits"
    assert snap["visit_count"] == 3

    listed = (await client.get(f"/trials/{trial_id}/soa-snapshots")).json()
    assert [s["id"] for s in listed] == [snap["id"]]


async def test_restore_replaces_current_soa_and_takes_pre_restore_snapshot(
    client: AsyncClient, trial_with_soa: dict
) -> None:
    """The whole point of snapshots: revert a bad change."""
    trial_id = trial_with_soa["trial"]["id"]
    arm_id = trial_with_soa["arm"]["id"]

    # Snapshot the original 3-visit SoA.
    snap = (
        await client.post(
            f"/trials/{trial_id}/soa-snapshots", json={"label": "original"}
        )
    ).json()

    # Mess up the SoA — add a bogus visit, delete the randomization one.
    visits = (await client.get(f"/arms/{arm_id}/visits")).json()
    rand = next(v for v in visits if v["visit_type"] == "randomization")
    await client.delete(f"/arms/{arm_id}/visits/{rand['id']}")
    await client.post(
        f"/arms/{arm_id}/visits",
        json={
            "name": "Bogus",
            "visit_type": "other",
            "target_day_offset": 99,
            "window_days": 0,
            "sort_order": 99,
        },
    )
    after_mess = (await client.get(f"/arms/{arm_id}/visits")).json()
    assert len(after_mess) == 3
    assert "Bogus" in {v["name"] for v in after_mess}
    assert "Randomization" not in {v["name"] for v in after_mess}

    # Restore the original — should bring back Randomization and drop Bogus.
    res = await client.post(f"/soa-snapshots/{snap['id']}/restore")
    assert res.status_code == 200, res.text
    after_restore = (await client.get(f"/arms/{arm_id}/visits")).json()
    names = {v["name"] for v in after_restore}
    assert names == {"Screening", "Randomization", "Week 4"}

    # And a pre_restore snapshot was taken automatically so the user can
    # un-restore.
    snaps = (await client.get(f"/trials/{trial_id}/soa-snapshots")).json()
    reasons = [s["reason"] for s in snaps]
    assert "pre_restore" in reasons


async def test_snapshots_are_org_scoped(
    client: AsyncClient, trial_with_soa: dict
) -> None:
    trial_id = trial_with_soa["trial"]["id"]
    snap = (
        await client.post(
            f"/trials/{trial_id}/soa-snapshots", json={"label": "only-A"}
        )
    ).json()

    # Switch to a different org — should not see Org A's snapshot.
    b = await _signup(client, "RlsBSnap")
    await _login(client, b["id"], "admin@rlsbsnap.example.com")
    # GET on Org A's trial — 404 (RLS blocks).
    res = await client.get(f"/trials/{trial_id}/soa-snapshots")
    assert res.status_code == 404
    # POST restore on Org A's snapshot — 404 (RLS blocks).
    res = await client.post(f"/soa-snapshots/{snap['id']}/restore")
    assert res.status_code == 404
