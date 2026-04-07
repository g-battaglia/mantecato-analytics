"""
Geo route — GET /api/sites/{siteId}/geo
Supports country/region/city levels with optional filters.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, parse_filters, resolve_dates
from mantecato_core.queries import geo as q_geo

router = APIRouter(prefix="/api/sites/{site_id}", tags=["geo"])


@router.get("/geo")
async def get_geo(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    level: str = Query("country"),
    country: str | None = Query(None),
    region: str | None = Query(None),
    page: str | None = Query(None, alias="page"),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)
    return await q_geo.get_geo_metrics(
        site_id, start_date, end_date, level, country, region, page, 50, filters
    )
