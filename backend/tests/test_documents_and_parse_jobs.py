"""Phase 5 gate — document upload + SoA parse job lifecycle.

These tests exercise the API surface end-to-end against real Postgres + real
MinIO, but mock both the arq enqueue (no real worker) and the Claude call.
The parse_soa worker is exercised separately in test_soa_parser_worker.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.soa_parse_job import SoaParseJob, SoaParseJobStatus
from app.storage import ensure_bucket


async def _signup(client: AsyncClient, name: str = "P5Org") -> dict:
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


@pytest.fixture(scope="session", autouse=True)
async def _bucket() -> None:
    """Ensure the dev bucket exists before any test runs."""
    await ensure_bucket()


@pytest.fixture
async def trial_setup(client: AsyncClient) -> dict:
    """Org + admin login + a trial with a default arm. Returns the IDs."""
    org = await _signup(client, "P5Org")
    await _login(client, org["id"], "admin@p5org.example.com")
    trial = (
        await client.post(
            "/trials",
            json={
                "name": "Phase 5 Trial",
                "fpfv": "2026-01-05",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
                "enrollment_target": 100,
                "screening_target": 125,
            },
        )
    ).json()
    arm = (await client.get(f"/trials/{trial['id']}/arms")).json()[0]
    return {"org_id": org["id"], "trial_id": trial["id"], "arm_id": arm["id"]}


def _fake_pdf() -> bytes:
    """Smallest valid-looking PDF. Real Claude calls aren't made here so
    content doesn't matter — only that the API accepts the content_type."""
    return b"%PDF-1.4\n%fake\n%%EOF\n"


# --- 1. Upload writes document + enqueues parse job ----------------------


async def test_upload_creates_document_and_enqueues_job(
    client: AsyncClient, trial_setup: dict
) -> None:
    trial_id = trial_setup["trial_id"]

    with patch("app.routers.documents._enqueue_parse", new=AsyncMock()) as enqueue:
        res = await client.post(
            f"/trials/{trial_id}/documents",
            files={"file": ("protocol.pdf", _fake_pdf(), "application/pdf")},
        )
        assert res.status_code == 201, res.text
        job_body = res.json()
        assert job_body["status"] == "queued"
        assert UUID(job_body["document_id"])
        assert job_body["trial_id"] == trial_id
        # Worker was enqueued with the right IDs.
        enqueue.assert_called_once()
        args = enqueue.call_args.args
        assert args[0] == UUID(job_body["document_id"])
        assert args[1] == UUID(trial_setup["org_id"])
        assert args[2] == UUID(job_body["id"])


async def test_upload_rejects_non_pdf(client: AsyncClient, trial_setup: dict) -> None:
    res = await client.post(
        f"/trials/{trial_setup['trial_id']}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


async def test_upload_rejects_empty_file(
    client: AsyncClient, trial_setup: dict
) -> None:
    res = await client.post(
        f"/trials/{trial_setup['trial_id']}/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400


# --- 2. Apply writes Visit rows (the load-bearing PRD §10.2 path) -------


async def test_apply_writes_visits_to_arm(
    client: AsyncClient, trial_setup: dict
) -> None:
    """The load-bearing assertion: parsed_visits transition from JSONB to real
    Visit rows ONLY through the apply endpoint (PRD §10.2 mitigation)."""
    trial_id = trial_setup["trial_id"]
    arm_id = trial_setup["arm_id"]

    # Upload (and enqueue) — then we'll directly munge the job row to
    # simulate a successful parse (worker is exercised in its own test).
    with patch("app.routers.documents._enqueue_parse", new=AsyncMock()):
        res = await client.post(
            f"/trials/{trial_id}/documents",
            files={"file": ("p.pdf", _fake_pdf(), "application/pdf")},
        )
    job_id = res.json()["id"]

    # Force the job to "succeeded" with mock parsed_visits.
    engine = create_async_engine(get_settings().database_url_admin)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        job = await session.get(SoaParseJob, UUID(job_id))
        assert job is not None
        job.status = SoaParseJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        job.parsed_visits = [
            {
                "name": "Screening",
                "visit_type": "screening",
                "target_day_offset": -14,
                "window_days": 3,
                "confidence": 0.95,
                "flagged_reason": None,
            },
            {
                "name": "Randomization",
                "visit_type": "randomization",
                "target_day_offset": 0,
                "window_days": 0,
                "confidence": 0.99,
                "flagged_reason": None,
            },
            {
                "name": "Week 4 FU",
                "visit_type": "follow_up",
                "target_day_offset": 28,
                "window_days": 3,
                "confidence": 0.65,
                "flagged_reason": "window inferred from text",
            },
        ]
    await engine.dispose()

    # Confirm the visits don't exist yet (proves the apply is what writes them).
    res = await client.get(f"/arms/{arm_id}/visits")
    assert res.json() == []

    # Apply with the user-confirmed payload (they may have edited names/values).
    res = await client.post(
        f"/parse-jobs/{job_id}/apply",
        json={
            "arm_id": arm_id,
            "visits": [
                {
                    "name": "Screening",
                    "visit_type": "screening",
                    "target_day_offset": -14,
                    "window_days": 3,
                    "confidence": 0.95,
                    "flagged_reason": None,
                },
                {
                    "name": "Randomization",
                    "visit_type": "randomization",
                    "target_day_offset": 0,
                    "window_days": 0,
                    "confidence": 0.99,
                    "flagged_reason": None,
                },
                {
                    # User edited the flagged row's window after review.
                    "name": "Week 4 Follow-up",
                    "visit_type": "follow_up",
                    "target_day_offset": 28,
                    "window_days": 4,
                    "confidence": 0.95,  # user confirmed → bumped up
                    "flagged_reason": None,
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    created = res.json()
    assert len(created) == 3

    # The visits are now real rows.
    res = await client.get(f"/arms/{arm_id}/visits")
    visits = res.json()
    assert len(visits) == 3
    # The user's edits stuck — not Claude's original.
    fu = next(v for v in visits if v["name"] == "Week 4 Follow-up")
    assert fu["window_days"] == 4

    # Job is now APPLIED.
    res = await client.get(f"/parse-jobs/{job_id}")
    assert res.json()["status"] == "applied"


# --- 3. Discard doesn't write visits ------------------------------------


async def test_discard_does_not_write_visits(
    client: AsyncClient, trial_setup: dict
) -> None:
    trial_id = trial_setup["trial_id"]
    arm_id = trial_setup["arm_id"]

    with patch("app.routers.documents._enqueue_parse", new=AsyncMock()):
        res = await client.post(
            f"/trials/{trial_id}/documents",
            files={"file": ("p.pdf", _fake_pdf(), "application/pdf")},
        )
    job_id = res.json()["id"]

    # Make it succeeded so discard is allowed.
    engine = create_async_engine(get_settings().database_url_admin)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        job = await session.get(SoaParseJob, UUID(job_id))
        assert job is not None
        job.status = SoaParseJobStatus.SUCCEEDED
        job.parsed_visits = [
            {
                "name": "X",
                "visit_type": "randomization",
                "target_day_offset": 0,
                "window_days": 0,
                "confidence": 0.9,
                "flagged_reason": None,
            }
        ]
    await engine.dispose()

    res = await client.post(f"/parse-jobs/{job_id}/discard")
    assert res.status_code == 204

    # No visits written.
    res = await client.get(f"/arms/{arm_id}/visits")
    assert res.json() == []
    # Job is now DISCARDED.
    res = await client.get(f"/parse-jobs/{job_id}")
    assert res.json()["status"] == "discarded"


# --- 4. Replay: applying a stored raw_output works without re-calling Claude


async def test_apply_works_without_re_calling_claude(
    client: AsyncClient, trial_setup: dict
) -> None:
    """Proves the parser output is the durable artifact — apply is a pure
    DB-write operation that doesn't touch the Claude API. Re-applying a stored
    job's parsed_visits costs nothing in API tokens."""
    trial_id = trial_setup["trial_id"]
    arm_id = trial_setup["arm_id"]

    # Upload + manually mark succeeded (no enqueue, no Claude).
    with patch("app.routers.documents._enqueue_parse", new=AsyncMock()):
        res = await client.post(
            f"/trials/{trial_id}/documents",
            files={"file": ("p.pdf", _fake_pdf(), "application/pdf")},
        )
    job_id = res.json()["id"]

    engine = create_async_engine(get_settings().database_url_admin)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        job = await session.get(SoaParseJob, UUID(job_id))
        assert job is not None
        job.status = SoaParseJobStatus.SUCCEEDED
        job.raw_output = {"model": "claude-opus-4-7", "saved": "at parse time"}
        job.parsed_visits = [
            {
                "name": "Rand",
                "visit_type": "randomization",
                "target_day_offset": 0,
                "window_days": 0,
                "confidence": 0.99,
                "flagged_reason": None,
            }
        ]
    await engine.dispose()

    # Patch the parser to blow up — if apply ever calls it, this test fails.
    with patch(
        "app.services.claude_soa.parse_async",
        new=AsyncMock(side_effect=RuntimeError("apply must not call Claude")),
    ):
        res = await client.post(
            f"/parse-jobs/{job_id}/apply",
            json={
                "arm_id": arm_id,
                "visits": [
                    {
                        "name": "Rand",
                        "visit_type": "randomization",
                        "target_day_offset": 0,
                        "window_days": 0,
                        "confidence": 0.99,
                        "flagged_reason": None,
                    }
                ],
            },
        )
    assert res.status_code == 200, res.text


# --- 5. RLS isolation ----------------------------------------------------


async def test_rls_blocks_cross_org_document_reads(client: AsyncClient) -> None:
    org_a = await _signup(client, "RlsADoc")
    await _login(client, org_a["id"], "admin@rlsadoc.example.com")
    trial_a = (
        await client.post(
            "/trials",
            json={
                "name": "A",
                "fpfv": "2026-01-05",
                "lpfv": "2028-01-03",
                "lplv": "2029-01-01",
            },
        )
    ).json()
    with patch("app.routers.documents._enqueue_parse", new=AsyncMock()):
        res = await client.post(
            f"/trials/{trial_a['id']}/documents",
            files={"file": ("p.pdf", _fake_pdf(), "application/pdf")},
        )
    job_a_id = res.json()["id"]
    doc_a_id = res.json()["document_id"]

    org_b = await _signup(client, "RlsBDoc")
    await _login(client, org_b["id"], "admin@rlsbdoc.example.com")
    res = await client.get(f"/documents/{doc_a_id}")
    assert res.status_code == 404
    res = await client.get(f"/parse-jobs/{job_a_id}")
    assert res.status_code == 404
