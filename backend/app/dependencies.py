"""
FastAPI dependencies for authentication and authorization.

- get_current_user: reads JWT or API key from Authorization: Bearer header
- require_site_access: additionally checks website access
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import verify_session_token, can_access_website
from mantecato_core.queries import api_keys as q_api_keys


_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """
    Extract the current user from Authorization: Bearer header.
    The token can be either a JWT session token or an API key (mtk_...).
    """
    token = credentials.credentials

    # Try API key first (prefixed with mtk_)
    if token.startswith("mtk_"):
        result = await q_api_keys.validate_api_key(token)
        if result:
            return {
                "userId": result["userId"],
                "username": "__api_key__",
                "role": "api_key",
                "scopes": result["scopes"],
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Try JWT session token
    payload = verify_session_token(token)
    if payload:
        return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
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
        if not await can_access_website(user["userId"], "api_key", site_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have access to this site",
            )
    elif not await can_access_website(user["userId"], user["role"], site_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    user["_siteId"] = site_id
    return user


def parse_filters(request: Request) -> list:
    """Parse filter parameters from the request query string."""
    from mantecato_core.filters import parse_filters_from_params

    return parse_filters_from_params(request.query_params.getlist("f"))


def require_scope(scope: str):
    """Dependency factory that checks if the authenticated user has the given scope."""

    async def _check(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if user.get("role") == "api_key":
            scopes = user.get("scopes", [])
            if scope not in scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key missing required scope: {scope}",
                )
        return user

    return _check
