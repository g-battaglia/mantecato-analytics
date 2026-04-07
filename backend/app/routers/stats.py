"""
Stats route — GET /api/sites/{siteId}/stats
Supports optional `section` param for partial responses, otherwise returns all 9 queries.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import get_comparison_range
from ..dependencies import require_site_access, parse_filters, resolve_dates
from mantecato_core.queries import stats as q_stats
from mantecato_core.queries import sources as q_sources

router = APIRouter(prefix="/api/sites/{site_id}", tags=["stats"])




@router.get("/stats")
async def get_stats(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    granularity: str = Query("day"),
    section: str | None = Query(None),
    mode: str = Query("path"),
    normalize: str = Query("smart"),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)
    normalize_urls: bool | str = False if normalize == "off" else normalize

    # Section-based partial responses
    if section:
        if section == "metrics":
            return await q_stats.get_website_stats(
                site_id, start_date, end_date, filters
            )
        if section == "timeseries":
            return await q_stats.get_pageview_time_series(
                site_id, start_date, end_date, granularity, filters
            )
        if section == "pages":
            page_mode = "slug" if mode == "slug" else "path"
            return await q_stats.get_top_pages(
                site_id, start_date, end_date, 10, filters, page_mode, normalize_urls
            )
        if section == "referrers":
            return await q_stats.get_top_referrers(
                site_id, start_date, end_date, 10, filters
            )
        if section == "events":
            return await q_stats.get_top_events(
                site_id, start_date, end_date, 10, filters
            )
        if section == "browsers":
            return await q_stats.get_device_breakdown(
                site_id, start_date, end_date, "browser", 10, filters
            )
        if section == "os":
            return await q_stats.get_device_breakdown(
                site_id, start_date, end_date, "os", 10, filters
            )
        if section == "devices":
            return await q_stats.get_device_breakdown(
                site_id, start_date, end_date, "device", 10, filters
            )
        if section == "countries":
            return await q_stats.get_country_breakdown(
                site_id, start_date, end_date, 10, filters
            )
        if section == "sections":
            return await q_stats.get_top_sections(
                site_id, start_date, end_date, 2, 10, filters, normalize_urls
            )

    # Full response — calculate previous period
    prev_range = get_comparison_range(
        type("DateRange", (), {"start_date": start_date, "end_date": end_date})(),
        "previous_period",
    )

    results = await asyncio.gather(
        q_stats.get_website_stats(site_id, start_date, end_date, filters),
        q_stats.get_website_stats(
            site_id, prev_range.start_date, prev_range.end_date, filters
        ),
        q_stats.get_pageview_time_series(
            site_id, start_date, end_date, granularity, filters
        ),
        q_stats.get_pageview_time_series(
            site_id, prev_range.start_date, prev_range.end_date, granularity, filters
        ),
        q_stats.get_top_pages(
            site_id,
            start_date,
            end_date,
            10,
            filters,
            "slug" if mode == "slug" else "path",
            normalize_urls,
        ),
        q_stats.get_top_referrers(site_id, start_date, end_date, 10, filters),
        q_stats.get_top_events_with_properties(
            site_id, start_date, end_date, 10, 3, filters
        ),
        q_stats.get_device_breakdown(
            site_id, start_date, end_date, "browser", 10, filters
        ),
        q_stats.get_country_breakdown(site_id, start_date, end_date, 10, filters),
        q_stats.get_top_sections(site_id, start_date, end_date, 2, 10, filters, normalize_urls),
        q_sources.get_channel_metrics(site_id, start_date, end_date, filters),
    )

    return {
        "stats": results[0],
        "previousStats": results[1],
        "timeseries": results[2],
        "previousTimeseries": results[3],
        "pages": results[4],
        "referrers": results[5],
        "events": results[6],
        "browsers": results[7],
        "countries": results[8],
        "sections": results[9],
        "channels": results[10],
    }
