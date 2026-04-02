"""
Revenue route — GET /api/sites/{siteId}/revenue
Returns summary, timeseries, by-event, and by-country breakdowns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access
from ..queries import revenue as q_revenue

router = APIRouter(prefix="/api/sites/{site_id}", tags=["revenue"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


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
    start_date, end_date = _resolve_dates(preset, start, end)

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
