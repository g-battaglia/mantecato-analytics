"""
Devices route — GET /api/sites/{siteId}/devices
Returns browsers, os, devices, screens, languages breakdowns in parallel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range
from ..dependencies import require_site_access, parse_filters
from mantecato_core.queries import devices as q_devices

router = APIRouter(prefix="/api/sites/{site_id}", tags=["devices"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/devices")
async def get_devices(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    filters: list = Depends(parse_filters),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)

    results = await asyncio.gather(
        q_devices.get_device_metrics(
            site_id, start_date, end_date, "browser", 20, filters
        ),
        q_devices.get_device_metrics(site_id, start_date, end_date, "os", 20, filters),
        q_devices.get_device_metrics(
            site_id, start_date, end_date, "device", 20, filters
        ),
        q_devices.get_device_metrics(
            site_id, start_date, end_date, "screen", 20, filters
        ),
        q_devices.get_device_metrics(
            site_id, start_date, end_date, "language", 20, filters
        ),
    )

    return {
        "browsers": results[0],
        "os": results[1],
        "devices": results[2],
        "screens": results[3],
        "languages": results[4],
    }
