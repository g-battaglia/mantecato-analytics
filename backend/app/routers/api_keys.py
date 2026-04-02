"""
API keys routes — list/create/delete at /api/api-keys
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_current_user
from ..models import ApiKeyCreate
from ..queries import api_keys as q_api_keys

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


class ApiKeyDelete(BaseModel):
    id: str


@router.get("")
async def list_api_keys(
    user: dict = Depends(get_current_user),
):
    return await q_api_keys.list_api_keys(user["userId"])


@router.post("")
async def create_api_key(
    body: ApiKeyCreate,
    user: dict = Depends(get_current_user),
):
    result = await q_api_keys.create_api_key(user["userId"], body.name, body.scopes)
    return result


@router.delete("")
async def delete_api_key(
    body: ApiKeyDelete,
    user: dict = Depends(get_current_user),
):
    deleted = await q_api_keys.delete_api_key(body.id, user["userId"])
    if not deleted:
        return {"error": "API key not found or not owned by you"}
    return {"deleted": True}
