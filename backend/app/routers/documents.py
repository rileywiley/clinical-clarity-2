"""Documents + SoA parse jobs (PRD §7.1 / §10.2 / Phase 5).

Endpoint surface:
  POST   /trials/{trial_id}/documents           (multipart upload, enqueues parse)
  GET    /documents/{document_id}
  GET    /trials/{trial_id}/parse-jobs
  GET    /parse-jobs/{parse_job_id}
  GET    /parse-jobs/{parse_job_id}/parsed-visits
  POST   /parse-jobs/{parse_job_id}/apply
  POST   /parse-jobs/{parse_job_id}/discard

Write paths gate to Org Admin or Ops Lead. The Apply endpoint is the only
place parser output transitions from proposed (JSONB) to committed (Visit
rows) — PRD §10.2 mitigation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db, require_role
from app.models.base import new_uuid
from app.models.document import Document, DocumentKind, DocumentStatus
from app.models.soa_parse_job import SoaParseJob, SoaParseJobStatus
from app.models.trial import Arm, Trial
from app.models.user import User, UserRole
from app.models.visit import Visit, VisitType
from app.schemas.documents import DocumentOut
from app.schemas.soa_parse_job import (
    SoaParseJobApplyIn,
    SoaParseJobDetailOut,
    SoaParseJobOut,
)
from app.storage import store_file

router = APIRouter(tags=["documents"])

WRITE_ROLES = (UserRole.ORG_ADMIN, UserRole.OPS_LEAD)


async def _enqueue_parse(document_id: UUID, org_id: UUID, parse_job_id: UUID) -> None:
    """Enqueue the parse_soa job on the arq queue."""
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job(
            "parse_soa",
            str(document_id),
            str(org_id),
            str(parse_job_id),
        )
    finally:
        await pool.close(close_connection_pool=True)


# --- Document upload --------------------------------------------------


@router.post(
    "/trials/{trial_id}/documents",
    response_model=SoaParseJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def upload_document(
    trial_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SoaParseJobOut:
    """Multipart upload of a protocol PDF. Persists the document, uploads to
    S3, enqueues a SoaParseJob, returns the parse job (frontend polls it).
    """
    trial = await db.get(Trial, trial_id)
    if trial is None or trial.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="trial not found")

    if file.content_type not in ("application/pdf",):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only application/pdf is supported in v1",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty file")
    # Soft cap at 20 MB — real protocols are usually <5 MB; anything larger
    # is likely a mistake (scanned-image PDF, etc.) and would slow Claude.
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds 20 MB limit",
        )

    # Mint IDs up front so we can build the storage key before insert.
    doc_id = new_uuid()
    storage_key = await store_file(
        org_id=user.org_id,
        document_id=doc_id,
        original_filename=file.filename or "protocol.pdf",
        data=data,
        content_type=file.content_type,
    )

    doc = Document(
        id=doc_id,
        org_id=user.org_id,
        trial_id=trial_id,
        kind=DocumentKind.PROTOCOL_PDF,
        original_filename=file.filename or "protocol.pdf",
        storage_key=storage_key,
        content_type=file.content_type,
        size_bytes=len(data),
        uploaded_by=user.id,
        status=DocumentStatus.UPLOADED,
    )
    db.add(doc)

    job = SoaParseJob(
        org_id=user.org_id,
        document_id=doc_id,
        trial_id=trial_id,
        status=SoaParseJobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()
    job_id = job.id

    # Commit the DB rows before enqueuing — otherwise the worker could pick
    # up the job before the document row is visible. The deps machinery
    # auto-commits on yield exit, so we flush + capture ID then let the
    # request finish.
    await db.commit()
    await _enqueue_parse(doc_id, user.org_id, job_id)

    return SoaParseJobOut.model_validate(job)


# --- Document fetch ---------------------------------------------------


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None or doc.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return doc


# --- Parse job listing + detail ---------------------------------------


@router.get(
    "/trials/{trial_id}/parse-jobs",
    response_model=list[SoaParseJobOut],
)
async def list_parse_jobs(
    trial_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SoaParseJob]:
    trial = await db.get(Trial, trial_id)
    if trial is None or trial.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows = (
        await db.execute(
            select(SoaParseJob)
            .where(SoaParseJob.trial_id == trial_id)
            .order_by(SoaParseJob.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get(
    "/parse-jobs/{parse_job_id}",
    response_model=SoaParseJobOut,
)
async def get_parse_job(
    parse_job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SoaParseJob:
    job = await db.get(SoaParseJob, parse_job_id)
    if job is None or job.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return job


@router.get(
    "/parse-jobs/{parse_job_id}/parsed-visits",
    response_model=SoaParseJobDetailOut,
)
async def get_parsed_visits(
    parse_job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SoaParseJobDetailOut:
    """Returns the editable review payload. Only meaningful when status is
    SUCCEEDED — frontend gates the review UI on that."""
    job = await db.get(SoaParseJob, parse_job_id)
    if job is None or job.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return SoaParseJobDetailOut(
        id=job.id,
        document_id=job.document_id,
        trial_id=job.trial_id,
        status=job.status.value,
        model_id=job.model_id,
        prompt_version=job.prompt_version,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        parsed_visits=job.parsed_visits or [],
    )


# --- Apply: parsed → real Visit rows ---------------------------------


@router.post(
    "/parse-jobs/{parse_job_id}/apply",
    response_model=list[dict],
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def apply_parse_job(
    parse_job_id: UUID,
    payload: SoaParseJobApplyIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Write user-confirmed parsed visits to a trial arm as real Visit rows.

    PRD §10.2 mitigation in action: this is the only path where parser output
    becomes committed forecast input. The user's edits to confidence-flagged
    rows go through here (the payload is what they confirmed, not what
    Claude originally returned).
    """
    job = await db.get(SoaParseJob, parse_job_id)
    if job is None or job.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if job.status not in (
        SoaParseJobStatus.SUCCEEDED,
        SoaParseJobStatus.APPLIED,  # re-apply after edits is allowed
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"parse job is {job.status.value}; only succeeded jobs can be applied",
        )

    arm = await db.get(Arm, payload.arm_id)
    if arm is None or arm.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="arm not found")
    if job.trial_id is not None and arm.trial_id != job.trial_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="arm does not belong to this parse job's trial",
        )

    created: list[Visit] = []
    for i, spec in enumerate(payload.visits):
        v = Visit(
            id=uuid4(),
            org_id=user.org_id,
            arm_id=arm.id,
            name=spec.name,
            visit_type=VisitType(spec.visit_type),
            target_day_offset=spec.target_day_offset,
            window_days=spec.window_days,
            sort_order=i,
            confidence=spec.confidence,
            flagged_reason=spec.flagged_reason,
        )
        db.add(v)
        created.append(v)

    job.status = SoaParseJobStatus.APPLIED
    await db.flush()

    # Return a lightweight list of the new visit IDs + names — frontend uses
    # these to navigate to the pricing step.
    return [
        {
            "id": str(v.id),
            "name": v.name,
            "visit_type": v.visit_type.value,
            "target_day_offset": v.target_day_offset,
            "window_days": v.window_days,
            "confidence": v.confidence,
            "flagged_reason": v.flagged_reason,
        }
        for v in created
    ]


# --- Discard ----------------------------------------------------------


@router.post(
    "/parse-jobs/{parse_job_id}/discard",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def discard_parse_job(
    parse_job_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    job = await db.get(SoaParseJob, parse_job_id)
    if job is None or job.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if job.status == SoaParseJobStatus.APPLIED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="cannot discard an already-applied job"
        )
    job.status = SoaParseJobStatus.DISCARDED
    doc = await db.get(Document, job.document_id)
    if doc is not None:
        doc.status = DocumentStatus.DISCARDED
