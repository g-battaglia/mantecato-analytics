"""
FastAPI dependencies for authentication and authorization.

- get_current_user: reads JWT from the mantecato-session cookie
- require_site_access: additionally checks website access
- get_api_key_user: validates Bearer API key
"""

from __future__ import annotations

from typing import Any

from fastapi import Cookie, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import COOKIE_NAME, verify_session_token, can_access_website
from .queries import api_keys as q_api_keys


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    access_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """
    Extract the current user either from a session cookie or a Bearer API key.
    Returns the session payload dict with userId, username, role.
    """
    # Try session cookie first
    if access_token:
        payload = verify_session_token(access_token)
        if payload:
            return payload

    # Try Bearer API key
    if credentials:
        result = await q_api_keys.validate_api_key(credentials.credentials)
        if result:
            # API-key auth doesn't have username/role — synthesise a minimal payload
            return {
                "userId": result["userId"],
                "username": "__api_key__",
                "role": "api_key",
                "scopes": result["scopes"],
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


async def require_site_access(
    site_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Dependency that combines get_current_user with website access check.
    Returns the user payload if access is granted.
    """
    if user.get("role") == "api_key":
        # API keys inherit the same access as the user
        pass
    elif not await can_access_website(user["userId"], user["role"], site_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    user["_siteId"] = site_id
    return user


def parse_filters(request: Request) -> list:
    """Parse filter parameters from the request query string."""
    from .filters import parse_filters_from_params

    return parse_filters_from_params(request.query_params.getlist("f"))
