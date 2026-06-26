"""arq job: parse an uploaded protocol PDF into a structured SoA.

Flow:
  1. Mark SoaParseJob as `running`, stamp started_at.
  2. Read the PDF bytes from S3 via the storage layer.
  3. Call claude_soa.parse_async(). Inject a fresh AsyncAnthropic client.
  4. On success: persist parsed_visits + raw_output, mark `succeeded`.
  5. On failure: persist the error, mark `failed`. The Document goes back to
     `uploaded` so the user can retry.

The worker runs under app_owner (BYPASSRLS) so it can read/write rows across
tenants — but we still bind the tenant via SET LOCAL so any RLS-aware code
paths behave identically to the runtime path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from anthropic import AsyncAnthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.document import Document, DocumentStatus
from app.models.soa_parse_job import SoaParseJob, SoaParseJobStatus
from app.services import claude_soa
from app.storage import get_file


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def parse_soa(ctx: dict, document_id: str, org_id: str, parse_job_id: str) -> str:
    """Worker entry point. arq passes string UUIDs across the Redis boundary;
    we hydrate them to UUID locally. Returns the job ID for logging."""
    doc_id = UUID(document_id)
    o_id = UUID(org_id)
    job_id = UUID(parse_job_id)

    settings = get_settings()
    engine = create_async_engine(settings.database_url_admin)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # ---- 1. mark running ---------------------------------------------
        async with sm() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :v, true)"),
                {"v": str(o_id)},
            )
            job = await session.get(SoaParseJob, job_id)
            if job is None or job.org_id != o_id:
                raise RuntimeError(f"parse job {job_id} not found for org {o_id}")
            job.status = SoaParseJobStatus.RUNNING
            job.started_at = _utcnow()
            job.model_id = claude_soa.model_id()
            job.prompt_version = claude_soa.PROMPT_VERSION

            doc = await session.get(Document, doc_id)
            if doc is None or doc.org_id != o_id:
                raise RuntimeError(f"document {doc_id} not found for org {o_id}")
            doc.status = DocumentStatus.PARSING
            storage_key = doc.storage_key

        # ---- 2. fetch from S3 + 3. call Claude ---------------------------
        pdf_bytes = await get_file(storage_key)

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — SoA parsing requires a live API key"
            )
        anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            parsed, raw = await claude_soa.parse_async(
                pdf_bytes, client=anthropic_client
            )
        finally:
            await anthropic_client.close()

        # ---- 4. persist success ------------------------------------------
        async with sm() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :v, true)"),
                {"v": str(o_id)},
            )
            job = await session.get(SoaParseJob, job_id)
            doc = await session.get(Document, doc_id)
            assert job is not None and doc is not None
            job.status = SoaParseJobStatus.SUCCEEDED
            job.finished_at = _utcnow()
            job.parsed_visits = [v.model_dump() for v in parsed.visits]
            job.raw_output = raw
            doc.status = DocumentStatus.UPLOADED  # parsed but not yet applied
    except Exception as exc:
        # ---- 5. persist failure ------------------------------------------
        async with sm() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :v, true)"),
                {"v": str(o_id)},
            )
            job = await session.get(SoaParseJob, job_id)
            if job is not None:
                job.status = SoaParseJobStatus.FAILED
                job.finished_at = _utcnow()
                job.error = f"{type(exc).__name__}: {exc}"
            doc = await session.get(Document, doc_id)
            if doc is not None:
                doc.status = DocumentStatus.UPLOADED  # let user retry
        raise
    finally:
        await engine.dispose()

    return str(job_id)
