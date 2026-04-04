"""
Compare route — GET /api/sites/{siteId}/compare
Returns current + previous period stats for comparison.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range, get_comparison_range
from ..dependencies import require_site_access
from mantecato_core.queries import compare as q_compare

router = APIRouter(prefix="/api/sites/{site_id}", tags=["compare"])


@router.get("/compare")
async def get_compare(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    compare: str = Query("previous_period"),
):
    dr = resolve_date_range(range)
    if not dr:
        return {"error": "Invalid date range for comparison"}

    comp_range = get_comparison_range(dr, compare)

    stats = await q_compare.get_comparison_stats(
        site_id,
        dr.start_date,
        dr.end_date,
        comp_range.start_date,
        comp_range.end_date,
    )

    current = next((s for s in stats if s.get("period") == "current"), None)
    previous = next((s for s in stats if s.get("period") == "previous"), None)

    return {
        "current": current,
        "previous": previous,
        "currentRange": {
            "start": dr.start_date.isoformat(),
            "end": dr.end_date.isoformat(),
        },
        "previousRange": {
            "start": comp_range.start_date.isoformat(),
            "end": comp_range.end_date.isoformat(),
        },
    }
