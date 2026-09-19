"""Private async HTTP transport for MCP tools."""

from __future__ import annotations

from typing import Any

import httpx

from mantecato_mcp.config import load_config


class RemoteError(RuntimeError):
    pass


async def request(method: str, path: str, *, body: dict[str, Any] | None = None) -> Any:
    """Perform one authenticated request without following redirects."""
    config = load_config()
    async with httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.timeout,
        follow_redirects=False,
        headers={"Accept": "application/json"},
    ) as client:
        try:
            response = await client.request(
                method,
                path,
                json=body,
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
        except httpx.TimeoutException as exc:
            raise RemoteError("Mantecato request timed out") from exc
        except httpx.HTTPError as exc:
            raise RemoteError(f"Cannot reach the Mantecato server: {exc}") from exc
    if 300 <= response.status_code < 400:
        raise RemoteError("Server redirect refused to protect the API key")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RemoteError("Mantecato returned a non-JSON response") from exc
    if response.status_code >= 400:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            message = error.get("message") or f"HTTP {response.status_code}"
            code = error.get("code") or "API_ERROR"
        else:
            message, code = str(error), "API_ERROR"
        raise RemoteError(f"{code}: {message}")
    return payload


async def get(path: str) -> Any:
    return await request("GET", path)


async def post(path: str, body: dict[str, Any]) -> Any:
    return await request("POST", path, body=body)
