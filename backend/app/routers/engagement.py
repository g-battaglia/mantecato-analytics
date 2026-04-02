"""
Engagement route — GET /api/sites/{siteId}/engagement
Returns duration distribution, percentiles, duration by page, bounce by page, bounce by source.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access, parse_filters
from ..queries import engagement as q_engagement

router = APIRouter(prefix="/api/sites/{site_id}", tags=["engagement"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/engagement")
async def get_engagement(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    (
        distribution,
        percentiles,
        duration_by_page,
        bounce_by_page,
        bounce_by_source,
    ) = await asyncio.gather(
        q_engagement.get_duration_distribution(site_id, start_date, end_date, filters),
        q_engagement.get_duration_percentiles(site_id, start_date, end_date, filters),
        q_engagement.get_duration_by_page(site_id, start_date, end_date, 20, filters),
        q_engagement.get_bounce_rate_by_page(
            site_id, start_date, end_date, 20, filters
        ),
        q_engagement.get_bounce_rate_by_source(
            site_id, start_date, end_date, 20, filters
        ),
    )

    return {
        "distribution": distribution,
        "percentiles": percentiles,
        "durationByPage": duration_by_page,
        "bounceByPage": bounce_by_page,
        "bounceBySource": bounce_by_source,
    }
