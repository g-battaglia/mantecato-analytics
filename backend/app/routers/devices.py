"""
Devices route — GET /api/sites/{siteId}/devices
Returns browsers, os, devices, screens, languages breakdowns in parallel.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_site_access, parse_filters, resolve_dates
from mantecato_core.queries import devices as q_devices

router = APIRouter(prefix="/api/sites/{site_id}", tags=["devices"])


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
    start_date, end_date = await resolve_dates(site_id, preset, start, end)

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
