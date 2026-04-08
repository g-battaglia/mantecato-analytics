"""
Bot config route — GET/PUT /api/sites/{siteId}/bot-config
Per-site bot detection configuration.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from typing import Any

from ..dependencies import require_site_access
from mantecato_core.queries import bot_config as q_bot_config

router = APIRouter(prefix="/api/sites/{site_id}", tags=["bot-config"])


@router.get("/bot-config")
async def get_bot_config(
    site_id: str,
    user: dict = Depends(require_site_access),
):
    return await q_bot_config.get_bot_config_or_defaults(site_id)


@router.put("/bot-config")
async def update_bot_config(
    site_id: str,
    config: dict[str, Any] = Body(...),
    user: dict = Depends(require_site_access),
):
    return await q_bot_config.upsert_bot_config(
        user["userId"], site_id, config
    )


@router.post("/bot-config/reset")
async def reset_bot_config(
    site_id: str,
    user: dict = Depends(require_site_access),
):
    defaults = {**q_bot_config.DEFAULT_CONFIG, "enabled": True}
    return await q_bot_config.upsert_bot_config(
        user["userId"], site_id, defaults
    )
