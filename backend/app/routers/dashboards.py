"""
Dashboards routes — list/create at /api/dashboards
and get/update/delete at /api/dashboards/{dashboardId}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_current_user, require_scope
from ..models import DashboardCreate, DashboardUpdate
from mantecato_core.queries import dashboards as q_dashboards

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

EMPTY_DASHBOARD_CONFIG = {
    "version": 1,
    "columns": 12,
    "widgets": [],
    "dateRange": "30d",
}


@router.get("")
async def list_dashboards(
    user: dict = Depends(get_current_user),
    siteId: str | None = Query(None),
):
    return await q_dashboards.list_dashboards(user["userId"], siteId)


@router.post("")
async def create_dashboard(
    body: DashboardCreate,
    user: dict = Depends(get_current_user),
    _scope=Depends(require_scope("write")),
):
    dashboard = await q_dashboards.create_dashboard(
        user["userId"],
        body.websiteId,
        body.name,
        body.description,
        EMPTY_DASHBOARD_CONFIG,
    )
    return dashboard


@router.get("/{dashboard_id}")
async def get_dashboard(
    dashboard_id: str,
    user: dict = Depends(get_current_user),
):
    dashboard = await q_dashboards.get_dashboard(dashboard_id, user["userId"])
    if not dashboard:
        return {"error": "Not found"}
    return dashboard


@router.patch("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: str,
    body: DashboardUpdate,
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

    dashboard = await q_dashboards.update_dashboard(
        dashboard_id, user["userId"], updates
    )
    if not dashboard:
        return {"error": "Not found"}
    return dashboard


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    user: dict = Depends(get_current_user),
    _scope=Depends(require_scope("write")),
):
    deleted = await q_dashboards.delete_dashboard(dashboard_id, user["userId"])
    if not deleted:
        return {"error": "Not found"}
    return {"ok": True}
