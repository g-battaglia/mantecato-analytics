"""
Sources route — GET /api/sites/{siteId}/sources
Supports sub-views via `view` param: referrers, channels, utm, utm-detail, click-ids, hostnames, referrer-pages.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, parse_filters, resolve_dates
from mantecato_core.queries import sources as q_sources

router = APIRouter(prefix="/api/sites/{site_id}", tags=["sources"])


@router.get("/sources")
async def get_sources(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    view: str = Query("referrers"),
    referrer: str = Query("(direct)"),
    groupBy: str = Query("utm_source"),
    dimension: str = Query("utm_source"),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    if view == "referrer-pages":
        return await q_sources.get_referrer_pages(
            site_id, start_date, end_date, referrer, 20, filters
        )

    if view == "channels":
        return await q_sources.get_channel_metrics(
            site_id, start_date, end_date, filters
        )

    if view == "utm-detail":
        return await q_sources.get_utm_detail_metrics(
            site_id, start_date, end_date, dimension, 50, filters
        )

    if view == "utm":
        return await q_sources.get_utm_metrics(
            site_id, start_date, end_date, groupBy, 50, filters
        )

    if view == "click-ids":
        return await q_sources.get_click_id_metrics(
            site_id, start_date, end_date, filters
        )

    if view == "hostnames":
        return await q_sources.get_hostname_metrics(
            site_id, start_date, end_date, 50, filters
        )

    # Default: referrers
    return await q_sources.get_referrer_metrics(
        site_id, start_date, end_date, 50, filters
    )
