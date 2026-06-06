"""Mantecato Python SDK -- HTTP client core.

This module provides the :class:`MantecatoClient` base class that handles
authentication, HTTP transport, and error mapping for all Mantecato API calls.
Endpoint-specific methods live in sub-modules (analytics, dashboards, etc.)
and are attached as attributes on the client instance.

Typical usage::

    from mantecato_client import MantecatoClient

    with MantecatoClient("https://analytics.example.com", api_key="mtk_xxx") as client:
        sites = client.sites.list()
        overview = client.analytics.overview(sites[0]["id"], date_range="30d")
"""

from __future__ import annotations

from typing import Any

import httpx

from mantecato_client.exceptions import AuthError, MantecatoError, NotFoundError, ValidationError

# Maps HTTP status codes to specific exception subclasses.
# Any status >= 400 not in this map raises the base MantecatoError.
_ERROR_MAP: dict[int, type[MantecatoError]] = {
    400: ValidationError,
    401: AuthError,
    403: AuthError,
    404: NotFoundError,
}


class MantecatoClient:
    """Standalone HTTP client for the Mantecato analytics API.

    Authenticates via API key (``Authorization: Bearer mtk_...``) and provides
    namespaced endpoint groups as attributes: ``sites``, ``analytics``,
    ``dashboards``, ``api_keys``, and ``bot_config``.

    The client manages an ``httpx.Client`` instance internally and supports
    the context-manager protocol for clean resource teardown.  You can also
    inject a pre-configured ``httpx.Client`` for testing or proxy scenarios.

    Attributes:
        sites: :class:`SitesEndpoints` -- list tracked websites.
        analytics: :class:`AnalyticsEndpoints` -- read-only analytics queries.
        dashboards: :class:`DashboardsEndpoints` -- custom dashboard CRUD.
        api_keys: :class:`ApiKeysEndpoints` -- API key management.
        bot_config: :class:`BotConfigEndpoints` -- bot detection configuration.

    Usage::

        client = MantecatoClient("https://analytics.example.com", api_key="mtk_xxx")
        sites = client.sites.list()
        overview = client.analytics.overview("website-uuid", date_range="30d")

        # Or as a context manager:
        with MantecatoClient("https://...", api_key="mtk_xxx") as client:
            data = client.analytics.pages("uuid", date_range="7d")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        httpx_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the Mantecato API client.

        Args:
            base_url: Root URL of the Mantecato instance (e.g.
                ``"https://analytics.example.com"``).  Trailing slashes are
                stripped automatically.
            api_key: API key string (``mtk_...`` format) for authentication.
                Sent as ``Authorization: Bearer <api_key>`` on every request.
            timeout: HTTP request timeout in seconds (default 30.0).
                Only used when creating the internal ``httpx.Client``.
            httpx_client: Optional pre-configured ``httpx.Client`` to use
                instead of creating one.  When provided, the client is NOT
                closed on ``close()`` -- the caller retains ownership.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx_client or httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if httpx_client is None:
            self._owns_client = True
        else:
            self._owns_client = False

        from mantecato_client.analytics import AnalyticsEndpoints
        from mantecato_client.api_keys import ApiKeysEndpoints
        from mantecato_client.bot_config import BotConfigEndpoints
        from mantecato_client.dashboards import DashboardsEndpoints
        from mantecato_client.sites import SitesEndpoints

        self.sites = SitesEndpoints(self)
        self.analytics = AnalyticsEndpoints(self)
        self.dashboards = DashboardsEndpoints(self)
        self.api_keys = ApiKeysEndpoints(self)
        self.bot_config = BotConfigEndpoints(self)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Send an HTTP request to the Mantecato API and return the JSON response.

        Constructs the full URL from ``base_url + path``, strips ``None``
        values from query params, attaches the API key header, and maps
        HTTP error status codes to typed exceptions.

        Args:
            method: HTTP method (``"GET"``, ``"POST"``, etc.).
            path: API path (e.g. ``"/api/analytics/overview/"``).
            params: Optional query parameters.  Keys with ``None`` values
                are silently removed before sending.
            json_body: Optional JSON request body (for POST requests).

        Returns:
            Parsed JSON response body (typically a dict).

        Raises:
            ValidationError: On HTTP 400 (bad request / invalid params).
            AuthError: On HTTP 401 or 403 (invalid or missing API key).
            NotFoundError: On HTTP 404 (resource not found).
            MantecatoError: On any other HTTP error (>= 400).
        """
        url = f"{self._base_url}{path}"
        clean_params: dict[str, Any] | None = None
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}

        response = self._http.request(
            method,
            url,
            params=clean_params,
            json=json_body,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = {}
            message = body.get("error", f"HTTP {response.status_code}")
            exc_cls = _ERROR_MAP.get(response.status_code, MantecatoError)
            raise exc_cls(message, status_code=response.status_code, response_body=body)

        return response.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request.  Convenience wrapper around ``_request``."""
        return self._request("GET", path, params=params)

    def _post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        """Send a POST request with an optional JSON body."""
        return self._request("POST", path, json_body=json_body or {})

    def close(self) -> None:
        """Close the underlying HTTP client if it was created internally.

        If a custom ``httpx_client`` was provided to the constructor, this
        method is a no-op -- the caller retains ownership of that client.
        """
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> MantecatoClient:
        """Enter context manager -- returns ``self``."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit context manager -- calls ``close()``."""
        self.close()
