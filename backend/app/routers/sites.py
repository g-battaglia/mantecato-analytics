"""
Sites route — GET /api/sites returns the current user's websites.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import get_user_websites
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("")
async def list_sites(user: dict = Depends(get_current_user)):
    """Return websites the current user has access to."""
    websites = await get_user_websites(user["userId"], user["role"])
    return websites
