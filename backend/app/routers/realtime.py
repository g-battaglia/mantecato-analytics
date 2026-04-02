"""
Realtime route — GET /api/sites/{siteId}/realtime
Returns active visitors, recent events, and current pages.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from ..dependencies import require_site_access
from ..queries import realtime as q_realtime

router = APIRouter(prefix="/api/sites/{site_id}", tags=["realtime"])


@router.get("/realtime")
async def get_realtime(
    site_id: str,
    user: dict = Depends(require_site_access),
):
    active, events, pages = await asyncio.gather(
        q_realtime.get_active_visitors(site_id),
        q_realtime.get_recent_events(site_id),
        q_realtime.get_current_pages(site_id),
    )
    return {"active": active, "events": events, "pages": pages}
