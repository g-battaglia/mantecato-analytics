"""Private HTTP transport for the CLI. This is not a public Python SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from mantecato_cli.errors import ApiError

if TYPE_CHECKING:
    from mantecato_cli.config import ClientConfig


class ApiTransport:
    """Authenticated, no-redirect transport with bounded response parsing."""

    def __init__(self, config: ClientConfig, *, transport: httpx.BaseTransport | None = None):
        self._key = config.api_key
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, json=body)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {self._key}"},
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ApiError("The Mantecato request timed out.", code="TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise ApiError(
                f"Cannot reach the Mantecato server: {exc}", code="NETWORK_ERROR"
            ) from exc
        if 300 <= response.status_code < 400:
            raise ApiError(
                "The server returned a redirect; refusing to forward the API key.",
                status_code=response.status_code,
                code="REDIRECT_REFUSED",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                "The server returned a non-JSON response.",
                status_code=response.status_code,
                code="INVALID_RESPONSE",
            ) from exc
        if response.status_code >= 400:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(error, dict):
                message = str(error.get("message") or f"HTTP {response.status_code}")
                code = str(error.get("code") or "API_ERROR")
            else:
                message, code = str(error or f"HTTP {response.status_code}"), "API_ERROR"
            raise ApiError(message, status_code=response.status_code, code=code)
        return payload
