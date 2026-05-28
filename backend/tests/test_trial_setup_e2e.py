"""Phase 2 gate test — end-to-end trial setup + live-default reflow.

Walks the full Phase 2 surface: signup → site → trial draft → arms+visits →
site assignment → activate. Then exercises the live-default semantics by
PATCHing OrgSettings and confirming the resolution service returns the new
value (PRD §5.2, "defaults resolve live").
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, name: str = "Acme Trials") -> dict:
    res = await client.post(
        "/orgs",
        json={
            "org_name": name,
            "default_timezone": "America/New_York",
            "admin_email": f"admin@{name.lower().replace(' ', '')}.example.com",
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
    assert res.status_code == 204, res.text


@pytest.fixture
async def admin_session(client: AsyncClient) -> dict:
    """Sign up an org and log in as its admin. Returns dict with org/admin info."""
    org = await _signup(client, "Acme Trials")
    await _login(client, org["id"], "admin@acmetrials.example.com")
    return org


# --- Seeding on signup ---------------------------------------------------


async def test_signup_seeds_org_settings_and_three_curves(
    client: AsyncClient, admin_session: dict
) -> None:
    # Org settings exist with PRD §5.1 defaults.
    res = await client.get("/org-settings")
    assert res.status_code == 200, res.text
    settings = res.json()
    assert settings["dur_screening_hours"] == 5.0
    assert settings["dur_randomization_hours"] == 4.0
    assert settings["dur_follow_up_hours"] == 2.0
    assert settings["dur_other_hours"] == 3.0
    assert settings["util_threshold_green_max"] == 70.0
    assert settings["util_threshold_amber_max"] == 95.0
    assert settings["default_attrition_curve_id"] is not None

    # Three presets exist with the expected names + dropout values.
    res = await client.get("/attrition-curves")
    assert res.status_code == 200, res.text
    curves = {c["name"]: c for c in res.json()}
    assert {"Low", "Standard", "High"} <= curves.keys()
    assert curves["Low"]["total_dropout_pct"] == 0.10
    assert curves["Standard"]["total_dropout_pct"] == 0.20
    assert curves["High"]["total_dropout_pct"] == 0.35
    assert curves["Standard"]["is_preset"] is True
    # Standard is the org's default.
    assert settings["default_attrition_curve_id"] == curves["Standard"]["id"]


# --- Sites CRUD + validation ---------------------------------------------


async def test_create_site_and_validation(client: AsyncClient, admin_session: dict) -> None:
    res = await client.post(
        "/sites",
        json={
            "name": "Boston Main",
            "timezone": "America/New_York",
            "operating_weekdays": [0, 1, 2, 3, 4],
            "hours_per_day": 10.0,
            "rooms": 3,
        },
    )
    assert res.status_code == 201, res.text
    site = res.json()
    assert site["name"] == "Boston Main"

    # Validation: operating_weekdays out of range
    res = await client.post(
        "/sites",
        json={"name": "Bad", "timezone": "UTC", "operating_weekdays": [7]},
    )
    assert res.status_code == 422

    # Validation: hours_per_day must be > 0
    res = await client.post(
        "/sites",
        json={"name": "Bad2", "timezone": "UTC", "hours_per_day": 0},
    )
    assert res.status_code == 422


# --- Trial date-order validation -----------------------------------------


async def test_trial_date_order_rejected(client: AsyncClient, admin_session: dict) -> None:
    res = await client.post(
        "/trials",
        json={
            "name": "Backwards",
            "fpfv": "2026-12-01",
            "lpfv": "2026-06-01",  # before fpfv → reject
            "lplv": "2027-01-01",
        },
    )
    assert res.status_code == 422


# --- Full happy-path activation -----------------------------------------


async def test_full_trial_setup_activation_happy_path(
    client: AsyncClient, admin_session: dict
) -> None:
    # Site
    res = await client.post(
        "/sites",
        json={
            "name": "Boston Main",
            "timezone": "America/New_York",
            "operating_weekdays": [0, 1, 2, 3, 4],
            "hours_per_day": 10.0,
            "rooms": 3,
        },
    )
    assert res.status_code == 201, res.text
    site_id = res.json()["id"]

    # Trial — single-arm; the API auto-creates a Default Arm.
    res = await client.post(
        "/trials",
        json={
            "name": "ACME-001",
            "fpfv": "2026-06-01",
            "lpfv": "2027-06-01",
            "lplv": "2028-06-01",
            "enrollment_target": 100,
            "screening_target": 125,
        },
    )
    assert res.status_code == 201, res.text
    trial = res.json()
    trial_id = trial["id"]
    # Attrition curve defaulted to Standard (the org's default).
    assert trial["attrition_curve_id"] is not None

    # Arms — should have one auto-created.
    res = await client.get(f"/trials/{trial_id}/arms")
    arms = res.json()
    assert len(arms) == 1
    assert arms[0]["name"] == "Default Arm"
    arm_id = arms[0]["id"]

    # Visits — add one randomization + one follow-up (minimal SoA).
    res = await client.post(
        f"/arms/{arm_id}/visits",
        json={
            "name": "Randomization",
            "visit_type": "randomization",
            "target_day_offset": 0,
            "sort_order": 0,
        },
    )
    assert res.status_code == 201, res.text
    res = await client.post(
        f"/arms/{arm_id}/visits",
        json={
            "name": "FU Week 4",
            "visit_type": "follow_up",
            "target_day_offset": 28,
            "sort_order": 1,
        },
    )
    assert res.status_code == 201, res.text

    # Activate now — should fail: no site assigned yet.
    res = await client.post(f"/trials/{trial_id}/activate")
    assert res.status_code == 422
    failures = {f["reason"] for f in res.json()["detail"]["failures"]}
    assert "no_sites" in failures

    # Assign the site.
    res = await client.post(
        f"/trials/{trial_id}/sites",
        json={
            "site_id": site_id,
            "per_site_enrollment_target": 100,
            "per_site_screening_target": 125,
        },
    )
    assert res.status_code == 201, res.text

    # Activate succeeds now.
    res = await client.post(f"/trials/{trial_id}/activate")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"


# --- Activation failure: no randomization visit -------------------------


async def test_activation_requires_randomization_visit(
    client: AsyncClient, admin_session: dict
) -> None:
    # Site
    site = (
        await client.post(
            "/sites",
            json={"name": "S", "timezone": "UTC", "rooms": 1, "hours_per_day": 8},
        )
    ).json()

    # Trial with only a screening visit — should fail activation.
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "Screen-only",
                "fpfv": "2026-06-01",
                "lpfv": "2027-06-01",
                "lplv": "2028-06-01",
            },
        )
    ).json()
    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]
    await client.post(
        f"/arms/{arm['id']}/visits",
        json={
            "name": "Screening",
            "visit_type": "screening",
            "target_day_offset": -14,
        },
    )
    await client.post(
        f"/trials/{trial['id']}/sites",
        json={"site_id": site["id"]},
    )

    res = await client.post(f"/trials/{trial['id']}/activate")
    assert res.status_code == 422
    failures = {f["reason"] for f in res.json()["detail"]["failures"]}
    assert "no_randomization_visit" in failures


# --- Live-default reflow (PRD §5.2) -------------------------------------


async def test_orgsettings_patch_reflows_to_resolution(
    client: AsyncClient, admin_session: dict
) -> None:
    """The Phase 2 gate's load-bearing assertion: PATCH OrgSettings duration,
    then the resolution service reads the new value on the next call."""
    # Patch follow_up duration 2h → 3h.
    res = await client.patch("/org-settings", json={"dur_follow_up_hours": 3.0})
    assert res.status_code == 200, res.text
    assert res.json()["dur_follow_up_hours"] == 3.0

    # GET it back to confirm persistence.
    res = await client.get("/org-settings")
    assert res.json()["dur_follow_up_hours"] == 3.0

    # The resolution service reads OrgSettings live — we test it directly
    # rather than going through the engine wiring (which lands in Phase 4).
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings
    from app.models.org_settings import OrgSettings
    from app.models.user import User
    from app.models.visit import Visit, VisitType
    from app.services.resolution import resolve_visit_duration

    engine = create_async_engine(get_settings().database_url_admin)
    async with engine.connect() as conn:
        org_id = (
            (await conn.execute(select(User.org_id).limit(1))).scalar_one()
        )
    await engine.dispose()

    # Build a transient Visit (not persisted) to ask the resolver.
    fake_visit = Visit(
        org_id=org_id,
        arm_id=org_id,  # placeholder; resolver doesn't read FKs
        name="probe",
        visit_type=VisitType.FOLLOW_UP,
        target_day_offset=14,
        window_days=0,
    )

    # Use a session against the admin engine so we can read OrgSettings.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(get_settings().database_url_admin)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        settings_obj = (
            await session.execute(
                select(OrgSettings).where(OrgSettings.org_id == org_id)
            )
        ).scalar_one()
        dur = await resolve_visit_duration(session, fake_visit, None, settings_obj)
    await engine.dispose()

    assert dur == 3.0  # was 2.0 before the PATCH


# --- RLS isolation on Phase 2 tables ------------------------------------


async def test_rls_blocks_cross_org_trial_reads(client: AsyncClient) -> None:
    """Two orgs, each with their own site + trial. Org A cannot see org B's data."""
    org_a = await _signup(client, "Org A")
    await _login(client, org_a["id"], "admin@orga.example.com")
    await client.post("/sites", json={"name": "A-site", "timezone": "UTC"})
    await client.post(
        "/trials",
        json={
            "name": "A-trial",
            "fpfv": "2026-06-01",
            "lpfv": "2027-06-01",
            "lplv": "2028-06-01",
        },
    )

    org_b = await _signup(client, "Org B")
    await _login(client, org_b["id"], "admin@orgb.example.com")
    # B should see zero trials and zero sites.
    res = await client.get("/sites")
    assert res.status_code == 200
    assert res.json() == []
    res = await client.get("/trials")
    assert res.json() == []


# Ensure the existing Phase 0 e2e test in test_rls_isolation.py still works
# with the new signup that seeds OrgSettings + curves.
async def test_phase0_rls_test_still_compatible(client: AsyncClient) -> None:
    """Smoke: signup auto-seed shouldn't have broken the previous RLS test surface."""
    org = await _signup(client, "Compat Org")
    await _login(client, org["id"], "admin@compatorg.example.com")
    res = await client.get("/auth/me")
    assert res.status_code == 200
