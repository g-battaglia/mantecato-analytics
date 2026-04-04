"""
Filter values route — GET /api/sites/{siteId}/filter-values
Returns distinct values for a given filter column.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range
from ..dependencies import require_site_access
from mantecato_core.queries import filter_values as q_filter_values

router = APIRouter(prefix="/api/sites/{site_id}", tags=["filter-values"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/filter-values")
async def get_filter_values(
    site_id: str,
    user: dict = Depends(require_site_access),
    column: str = Query(None),
    search: str | None = Query(None),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    if not column:
        return {"error": "Missing column parameter"}

    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    return await q_filter_values.get_filter_values(
        site_id, column, start_date, end_date, search
    )
