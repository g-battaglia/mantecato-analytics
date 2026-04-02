"""
Sessions route — GET /api/sites/{siteId}/sessions
Supports list mode (default) and detail mode (?sessionId=<id>).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access, parse_filters
from ..queries import sessions as q_sessions

router = APIRouter(prefix="/api/sites/{site_id}", tags=["sessions"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/sessions")
async def get_sessions(
    site_id: str,
    user: dict = Depends(require_site_access),
    sessionId: str | None = Query(None),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    visitedPage: str | None = Query(None),
    triggeredEvent: str | None = Query(None),
    filters: list = Depends(parse_filters),
):
    # Detail view for a specific session
    if sessionId:
        activity = await q_sessions.get_session_activity(sessionId, site_id)
        return activity

    # List mode
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    return await q_sessions.get_session_list(
        site_id,
        start_date,
        end_date,
        limit,
        offset,
        filters,
        visitedPage,
        triggeredEvent,
    )
