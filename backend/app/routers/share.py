"""
Share route — GET /api/share/{shareId}/stats (public, no auth)
Public stats endpoint that looks up a website by shareId.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from mantecato_core.database import raw_query_one
from mantecato_core.date_utils import get_comparison_range
from ..dependencies import resolve_dates
from mantecato_core.queries import stats as q_stats

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/{share_id}/stats")
async def get_shared_stats(
    share_id: str,
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    granularity: str = Query("day"),
):
    # Look up website by shareId
    website = await raw_query_one(
        """SELECT website_id, name, domain, share_id
           FROM website
           WHERE share_id = {{shareId}}
             AND deleted_at IS NULL""",
        {"shareId": share_id},
    )

    if not website:
        return {"error": "Not found"}

    site_id = website["website_id"]
    preset = range

    # Resolve dates
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    prev_range = get_comparison_range(
        type("DateRange", (), {"start_date": start_date, "end_date": end_date})(),
        "previous_period",
    )

    results = await asyncio.gather(
        q_stats.get_website_stats(site_id, start_date, end_date),
        q_stats.get_website_stats(site_id, prev_range.start_date, prev_range.end_date),
        q_stats.get_pageview_time_series(site_id, start_date, end_date, granularity),
        q_stats.get_pageview_time_series(
            site_id, prev_range.start_date, prev_range.end_date, granularity
        ),
        q_stats.get_top_pages(site_id, start_date, end_date, 10),
        q_stats.get_top_referrers(site_id, start_date, end_date, 10),
        q_stats.get_top_events(site_id, start_date, end_date, 10),
        q_stats.get_device_breakdown(site_id, start_date, end_date, "browser", 10),
        q_stats.get_country_breakdown(site_id, start_date, end_date, 10),
    )

    return {
        "website": {"name": website["name"], "domain": website["domain"]},
        "stats": results[0],
        "previousStats": results[1],
        "timeseries": results[2],
        "previousTimeseries": results[3],
        "pages": results[4],
        "referrers": results[5],
        "events": results[6],
        "browsers": results[7],
        "countries": results[8],
    }
