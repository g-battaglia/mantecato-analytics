"""
Journeys route — GET /api/sites/{siteId}/journeys
User journey analysis with configurable path length.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access
from ..queries import journeys as q_journeys

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
    if preset == "custom" and start and end:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    else:
        dr = resolve_date_range(preset)
        if not dr:
            start_date = datetime(2020, 1, 1)
            end_date = datetime.utcnow()
        else:
            start_date = dr.start_date
            end_date = dr.end_date

    return await q_journeys.get_journeys(
        site_id, start_date, end_date, pathLength, limit
    )
