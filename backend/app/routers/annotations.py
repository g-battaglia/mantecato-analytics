"""
Annotations route — GET/POST/DELETE /api/sites/{siteId}/annotations
CRUD operations for annotations stored in the report table.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from mantecato_core.date_utils import resolve_date_range
from ..dependencies import require_site_access, require_scope
from ..models import AnnotationCreate
from mantecato_core.queries import annotations as q_annotations

router = APIRouter(prefix="/api/sites/{site_id}", tags=["annotations"])


def _resolve_dates(preset: str, custom_start: str | None, custom_end: str | None):
    if preset == "custom" and custom_start and custom_end:
        return datetime.fromisoformat(custom_start), datetime.fromisoformat(custom_end)
    dr = resolve_date_range(preset)
    if not dr:
        return datetime(2020, 1, 1), datetime.utcnow()
    return dr.start_date, dr.end_date


@router.get("/annotations")
async def list_annotations(
    site_id: str,
    user: dict = Depends(require_site_access),
    range: str = Query("30d", alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    preset = range
    start_date, end_date = _resolve_dates(preset, start, end)
    return await q_annotations.list_annotations(
        user["userId"], site_id, start_date, end_date
    )


@router.post("/annotations")
async def create_annotation(
    site_id: str,
    body: AnnotationCreate,
    user: dict = Depends(require_site_access),
    _scope=Depends(require_scope("write")),
):
    annotation = await q_annotations.create_annotation(
        user["userId"],
        site_id,
        body.title,
        body.description,
        body.date,
        body.color,
    )
    return annotation


@router.delete("/annotations")
async def delete_annotation(
    site_id: str,
    id: str = Query(None),
    user: dict = Depends(require_site_access),
    _scope=Depends(require_scope("write")),
):
    if not id:
        return {"error": "Missing id"}
    deleted = await q_annotations.delete_annotation(id, user["userId"])
    if not deleted:
        return {"error": "Not found"}
    return {"ok": True}
