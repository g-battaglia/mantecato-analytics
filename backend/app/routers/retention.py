"""
Retention route — GET /api/sites/{siteId}/retention
Cohort analysis with week/month granularity.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range
from ..dependencies import require_site_access
from mantecato_core.queries import retention as q_retention

router = APIRouter(prefix="/api/sites/{site_id}", tags=["retention"])


@router.get("/retention")
async def get_retention(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("90d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    cohortGranularity: str = Query("week"),
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

    return await q_retention.get_retention(
        site_id, start_date, end_date, cohortGranularity
    )
