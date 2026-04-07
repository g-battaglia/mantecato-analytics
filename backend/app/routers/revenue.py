"""
Revenue route — GET /api/sites/{siteId}/revenue
Returns summary, timeseries, by-event, and by-country breakdowns.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, resolve_dates
from mantecato_core.queries import revenue as q_revenue

router = APIRouter(prefix="/api/sites/{site_id}", tags=["revenue"])


@router.get("/revenue")
async def get_revenue(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    granularity: str = Query("day"),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    summary, timeseries, by_event, by_country = await asyncio.gather(
        q_revenue.get_revenue_summary(site_id, start_date, end_date),
        q_revenue.get_revenue_time_series(site_id, start_date, end_date, granularity),
        q_revenue.get_revenue_by_event(site_id, start_date, end_date),
        q_revenue.get_revenue_by_country(site_id, start_date, end_date),
    )

    return {
        "summary": summary,
        "timeseries": timeseries,
        "byEvent": by_event,
        "byCountry": by_country,
    }
