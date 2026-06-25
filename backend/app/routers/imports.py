"""Bulk CSV import endpoints (post-Phase-6).

Three kinds: sites, trials, projections. Two endpoints per kind shape:
preview (validates, no writes) and commit (validates, writes in one
transaction). Plus a download for the template CSV.

Role-gated to org_admin — same posture as Admin settings.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.models.user import User, UserRole
from app.services import csv_import

XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

router = APIRouter(prefix="/imports", tags=["imports"])

ADMIN_ONLY = (UserRole.ORG_ADMIN,)
Kind = Literal["sites", "trials", "projections"]


def _check_kind(kind: str) -> csv_import.ImportKind:
    if kind not in ("sites", "trials", "projections"):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"unknown import kind: {kind}",
        )
    return kind  # type: ignore[return-value]


async def _read_upload(file: UploadFile) -> str:
    """Normalize CSV or XLSX upload to CSV text for the validator."""
    raw = await file.read()
    text = csv_import.normalize_upload(file.filename or "upload.csv", raw)
    if not text.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty"
        )
    return text


@router.get("/templates/{kind}.csv")
async def download_template_csv(
    kind: str,
    _user: User = Depends(get_current_user),
) -> Response:
    k = _check_kind(kind)
    return Response(
        content=csv_import.template_for(k),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{kind}-template.csv"'
        },
    )


@router.get("/templates/{kind}.xlsx")
async def download_template_xlsx(
    kind: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Same template as the .csv endpoint, but as a 2-sheet workbook —
    Template (header + example rows) plus a Reference sheet listing the
    live names a user would otherwise have to remember (existing sites
    for the trials template, existing trials/arms for projections)."""
    k = _check_kind(kind)
    body = await csv_import.template_xlsx_for(k, user.org_id, db)
    return Response(
        content=body,
        media_type=XLSX_MEDIA,
        headers={
            "Content-Disposition": f'attachment; filename="{kind}-template.xlsx"'
        },
    )


@router.post(
    "/{kind}/preview",
    dependencies=[Depends(require_role(*ADMIN_ONLY))],
)
async def preview(
    kind: str,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    k = _check_kind(kind)
    text = await _read_upload(file)
    result = await csv_import.preview(k, text, user.org_id, db)
    return {
        "ok": result.ok,
        "actions": result.actions,
        "errors": [{"row": e.row, "message": e.message} for e in result.errors],
    }


@router.post(
    "/{kind}/commit",
    dependencies=[Depends(require_role(*ADMIN_ONLY))],
)
async def commit(
    kind: str,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    k = _check_kind(kind)
    text = await _read_upload(file)
    result = await csv_import.commit(k, text, user.org_id, db)
    if not result.ok:
        # The single-transaction guarantee: nothing was written. Surface a
        # 422 so the client treats it as a validation failure, not a 500.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": [
                    {"row": e.row, "message": e.message} for e in result.errors
                ]
            },
        )
    return {"ok": True, "actions": result.actions}
