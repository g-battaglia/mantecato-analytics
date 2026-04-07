"""
Journeys route — GET /api/sites/{siteId}/journeys
User journey analysis with configurable path length.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, resolve_dates
from mantecato_core.queries import journeys as q_journeys

router = APIRouter(prefix="/api/sites/{site_id}", tags=["journeys"])


@router.get("/journeys")
async def get_journeys(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    pathLength: int = Query(3),
    limit: int = Query(20),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    return await q_journeys.get_journeys(
        site_id, start_date, end_date, pathLength, limit
    )
