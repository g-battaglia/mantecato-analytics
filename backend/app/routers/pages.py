"""
Pages route — GET /api/sites/{siteId}/pages
Supports list mode (default) and detail mode (?page=<urlPath>).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range, resolve_granularity
from ..dependencies import require_site_access, parse_filters
from mantecato_core.queries import pageviews as q_pages

router = APIRouter(prefix="/api/sites/{site_id}", tags=["pages"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/pages")
async def get_pages(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    page: str | None = Query(None, alias="page"),
    granularity: str = Query("day"),
    limit: int = Query(50),
    offset: int = Query(0),
    mode: str = Query("path"),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    # Page detail mode
    if page:
        dr = resolve_date_range(preset)
        resolved_gran = resolve_granularity(granularity, dr) if dr else "day"

        timeseries = await q_pages.get_page_time_series(
            site_id, page, start_date, end_date, resolved_gran, filters
        )
        referrers = await q_pages.get_page_referrers(
            site_id, page, start_date, end_date, 10
        )
        next_pages = await q_pages.get_next_pages(
            site_id, page, start_date, end_date, 10
        )
        time_distribution = await q_pages.get_time_on_page_distribution(
            site_id, page, start_date, end_date
        )

        return {
            "timeseries": timeseries,
            "referrers": referrers,
            "nextPages": next_pages,
            "timeDistribution": time_distribution,
        }

    # List mode
    page_mode = "slug" if mode == "slug" else "path"
    pages = await q_pages.get_page_metrics(
        site_id, start_date, end_date, limit, offset, filters, page_mode
    )
    return pages
