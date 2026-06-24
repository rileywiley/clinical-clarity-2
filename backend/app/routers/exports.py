"""CSV export endpoints (PRD §7.4).

PDF export is client-side (browser Print to PDF + a print stylesheet) so
nothing for it lives here. CSV needs server-side composition because the
data is the engine's output, not the rendered DOM.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.site import Site
from app.models.user import User
from app.services.csv_export import cells_to_csv
from app.services.forecast_adapter import compute_network_forecast

router = APIRouter(tags=["exports"])


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _csv_response(body: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/forecast/network.csv")
async def network_forecast_csv(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> Response:
    today = date.today()
    f = _monday(from_date if from_date else today)
    t = to_date if to_date else f + timedelta(weeks=12)
    cells = await compute_network_forecast(
        db, user.org_id, today=today, horizon_end=t
    )
    in_range = [c for c in cells.values() if f <= c.week_start <= t]
    return _csv_response(
        cells_to_csv(in_range),
        f"network-forecast-{f.isoformat()}-to-{t.isoformat()}.csv",
    )


@router.get("/sites/{site_id}/forecast.csv")
async def site_forecast_csv(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> Response:
    site = await db.get(Site, site_id)
    if site is None or site.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    today = date.today()
    f = _monday(from_date if from_date else today)
    t = to_date if to_date else f + timedelta(weeks=18)
    cells = await compute_network_forecast(
        db, user.org_id, today=today, horizon_end=t, site_ids=[site_id]
    )
    in_range = [
        c
        for (sid, _wk), c in cells.items()
        if sid == str(site_id) and f <= c.week_start <= t
    ]
    return _csv_response(
        cells_to_csv(in_range),
        f"site-{site.name.replace(' ', '_')}-forecast-{f.isoformat()}-to-{t.isoformat()}.csv",
    )
