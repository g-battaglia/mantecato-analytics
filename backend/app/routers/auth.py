"""
Auth routes — POST /api/auth (login) and DELETE /api/auth (logout).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from ..auth import COOKIE_NAME, COOKIE_MAX_AGE, verify_credentials, create_session_token
from ..models import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("")
async def login(body: LoginRequest, response: Response):
    """Authenticate user and set session cookie."""
    session = await verify_credentials(body.username, body.password)
    if not session:
        return {"error": "Invalid username or password"}, 401

    token = create_session_token(session)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )

    return {
        "user": {
            "userId": session["userId"],
            "username": session["username"],
            "role": session["role"],
        }
    }


@router.delete("")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"success": True}
