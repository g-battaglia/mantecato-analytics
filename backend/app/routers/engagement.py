"""
Engagement route — GET /api/sites/{siteId}/engagement
Returns duration distribution, percentiles, duration by page, bounce by page, bounce by source.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, parse_filters, resolve_dates
from mantecato_core.queries import engagement as q_engagement

router = APIRouter(prefix="/api/sites/{site_id}", tags=["engagement"])


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
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

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


@router.get("/engagement/bucket-sessions")
async def get_bucket_sessions(
    site_id: str,
    user: dict = Depends(require_site_access),
    bucket: str = Query(..., description="Duration bucket name, e.g. '30m+'"),
    entry_page: str | None = Query(None, alias="entryPage"),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)
    return await q_engagement.get_sessions_for_bucket(
        site_id, start_date, end_date, bucket, limit, offset, filters, entry_page
    )
