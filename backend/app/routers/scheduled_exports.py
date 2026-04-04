"""
Scheduled exports routes — list/create at /api/scheduled-exports
and get/update/delete at /api/scheduled-exports/{exportId}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, require_scope
from ..models import ScheduledExportCreate, ScheduledExportUpdate
from mantecato_core.queries import scheduled_exports as q_scheduled_exports

router = APIRouter(prefix="/api/scheduled-exports", tags=["scheduled-exports"])


@router.get("")
async def list_scheduled_exports(
    user: dict = Depends(get_current_user),
):
    return await q_scheduled_exports.list_scheduled_exports(user["userId"])


@router.post("")
async def create_scheduled_export(
    body: ScheduledExportCreate,
    user: dict = Depends(get_current_user),
    _scope=Depends(require_scope("write")),
):
    config = body.config
    if (
        not config.get("websiteId")
        or not config.get("dataSource")
        or not config.get("format")
        or not config.get("schedule")
    ):
        return {
            "error": "name, config.websiteId, config.dataSource, config.format, and config.schedule are required"
        }

    result = await q_scheduled_exports.create_scheduled_export(
        user["userId"], body.name, body.description, config
    )
    return result


@router.get("/{export_id}")
async def get_scheduled_export(
    export_id: str,
    user: dict = Depends(get_current_user),
):
    result = await q_scheduled_exports.get_scheduled_export(export_id, user["userId"])
    if not result:
        return {"error": "Not found"}
    return result


@router.patch("/{export_id}")
async def update_scheduled_export(
    export_id: str,
    body: ScheduledExportUpdate,
    user: dict = Depends(get_current_user),
    _scope=Depends(require_scope("write")),
):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.config is not None:
        updates["config"] = body.config

    result = await q_scheduled_exports.update_scheduled_export(
        export_id, user["userId"], updates
    )
    if not result:
        return {"error": "Not found"}
    return result


@router.delete("/{export_id}")
async def delete_scheduled_export(
    export_id: str,
    user: dict = Depends(get_current_user),
    _scope=Depends(require_scope("write")),
):
    deleted = await q_scheduled_exports.delete_scheduled_export(
        export_id, user["userId"]
    )
    if not deleted:
        return {"error": "Not found"}
    return {"ok": True}
