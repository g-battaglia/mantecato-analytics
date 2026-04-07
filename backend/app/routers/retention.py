"""
Retention route — GET /api/sites/{siteId}/retention
Cohort analysis with week/month granularity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, resolve_dates
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
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    return await q_retention.get_retention(
        site_id, start_date, end_date, cohortGranularity
    )
