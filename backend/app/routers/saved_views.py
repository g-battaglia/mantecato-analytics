"""
Saved views routes — list/create at /api/sites/{siteId}/saved-views
and get/update/delete at /api/sites/{siteId}/saved-views/{viewId}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, require_site_access
from ..models import SavedViewCreate, SavedViewUpdate
from ..queries import saved_views as q_saved_views

router = APIRouter(prefix="/api/sites/{site_id}", tags=["saved-views"])


@router.get("/saved-views")
async def list_saved_views(
    site_id: str,
    user: dict = Depends(require_site_access),
):
    return await q_saved_views.list_saved_views(user["userId"], site_id)


@router.post("/saved-views")
async def create_saved_view(
    site_id: str,
    body: SavedViewCreate,
    user: dict = Depends(require_site_access),
):
    view = await q_saved_views.create_saved_view(
        user["userId"], site_id, body.name, body.description, body.config
    )
    return view


@router.get("/saved-views/{view_id}")
async def get_saved_view(
    view_id: str,
    user: dict = Depends(get_current_user),
):
    view = await q_saved_views.get_saved_view(view_id, user["userId"])
    if not view:
        return {"error": "Not found"}
    return view


@router.patch("/saved-views/{view_id}")
async def update_saved_view(
    view_id: str,
    body: SavedViewUpdate,
    user: dict = Depends(get_current_user),
):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.config is not None:
        updates["config"] = body.config

    view = await q_saved_views.update_saved_view(view_id, user["userId"], updates)
    if not view:
        return {"error": "Not found"}
    return view


@router.delete("/saved-views/{view_id}")
async def delete_saved_view(
    view_id: str,
    user: dict = Depends(get_current_user),
):
    deleted = await q_saved_views.delete_saved_view(view_id, user["userId"])
    if not deleted:
        return {"error": "Not found"}
    return {"ok": True}
