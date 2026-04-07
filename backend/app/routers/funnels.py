"""
Funnels route — GET /api/sites/{siteId}/funnels
Dynamic funnel analysis with configurable steps.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, resolve_dates
from mantecato_core.queries import funnels as q_funnels

router = APIRouter(prefix="/api/sites/{site_id}", tags=["funnels"])


@router.get("/funnels")
async def get_funnels(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    steps: str | None = Query(None),
    window: int = Query(60),
):
    preset = range
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

    if not steps:
        return {"error": "Missing steps parameter"}

    try:
        parsed_steps = json.loads(steps)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid steps parameter"}

    if not isinstance(parsed_steps, list) or len(parsed_steps) < 2:
        return {"error": "At least 2 steps are required"}

    return await q_funnels.get_funnel(
        site_id, start_date, end_date, parsed_steps, window
    )
