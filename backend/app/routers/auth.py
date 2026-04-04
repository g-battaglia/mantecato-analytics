"""
Auth routes — POST /api/auth (login).

Returns a JWT token in the response body. The client stores it and sends it
as Authorization: Bearer <token> on subsequent requests.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..auth import verify_credentials, create_session_token
from ..models import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("")
async def login(body: LoginRequest):
    """Authenticate user and return JWT token."""
    session = await verify_credentials(body.username, body.password)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_session_token(session)

    return {
        "token": token,
        "user": {
            "userId": session["userId"],
            "username": session["username"],
            "role": session["role"],
        },
    }
