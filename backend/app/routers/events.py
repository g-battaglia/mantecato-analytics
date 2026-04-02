"""
Events route — GET /api/sites/{siteId}/events
Supports list mode (default) and detail mode (?event=<eventName>).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from ..date_utils import resolve_date_range
from ..dependencies import require_site_access, parse_filters
from ..queries import events as q_events

router = APIRouter(prefix="/api/sites/{site_id}", tags=["events"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/events")
async def get_events(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    event: str | None = Query(None, alias="event"),
    granularity: str = Query("day"),
    section: str | None = Query(None),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    # Detail view for a specific event
    if event:
        if section == "timeseries":
            return await q_events.get_event_time_series(
                site_id, event, start_date, end_date, granularity, filters
            )
        if section == "properties":
            return await q_events.get_event_properties(
                site_id, event, start_date, end_date
            )

        # Default: return both timeseries + properties
        ts = await q_events.get_event_time_series(
            site_id, event, start_date, end_date, granularity, filters
        )
        props = await q_events.get_event_properties(
            site_id, event, start_date, end_date
        )
        return {"timeseries": ts, "properties": props}

    # List mode
    return await q_events.get_event_metrics(site_id, start_date, end_date, 50, filters)
