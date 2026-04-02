"""
Funnels route — GET /api/sites/{siteId}/funnels
Dynamic funnel analysis with configurable steps.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access
from ..queries import funnels as q_funnels

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
    if preset == "custom" and start and end:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    else:
        dr = resolve_date_range(preset)
        if not dr:
            start_date = datetime(2020, 1, 1)
            end_date = datetime.utcnow()
        else:
            start_date = dr.start_date
            end_date = dr.end_date

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
