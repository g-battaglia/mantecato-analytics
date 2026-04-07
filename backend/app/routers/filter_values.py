"""
Filter values route — GET /api/sites/{siteId}/filter-values
Returns distinct values for a given filter column.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, resolve_dates
from mantecato_core.queries import filter_values as q_filter_values

router = APIRouter(prefix="/api/sites/{site_id}", tags=["filter-values"])


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
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    return await q_filter_values.get_filter_values(
        site_id, column, start_date, end_date, search
    )
