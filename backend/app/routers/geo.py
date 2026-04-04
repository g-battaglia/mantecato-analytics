"""
Geo route — GET /api/sites/{siteId}/geo
Supports country/region/city levels with optional filters.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range
from ..dependencies import require_site_access, parse_filters
from mantecato_core.queries import geo as q_geo

router = APIRouter(prefix="/api/sites/{site_id}", tags=["geo"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


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
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)
    return await q_geo.get_geo_metrics(
        site_id, start_date, end_date, level, country, region, 50, filters
    )
