"""API key authentication middleware for CLI/MCP requests.

Inspects the ``Authorization: Bearer mtk_...`` header on every request.
When a valid API key is found, the request is annotated with user/scopes
attributes consumed by downstream views.

Behaviour:

- **No header** → request passes through unmodified (anonymous).
- **Valid key** → ``request.api_user``, ``request.api_key_scopes``, and
  ``request.is_api_authenticated`` are set.
- **Invalid/malformed key on ``/api/`` paths** → ``401 JSON`` response.
- **Invalid/malformed key on other paths** → request passes through (the web
  session auth layer handles authorization). This avoids breaking normal
  browser navigation for users who happen to have a stale token in localStorage.

The middleware delegates key verification to
:func:`apps.core.api_keys.validate_api_key`, which performs a SHA-256
lookup against the ``report`` table and updates ``lastUsedAt``.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.api_keys import validate_api_key

logger = logging.getLogger(__name__)

_PROTECTED_PREFIXES = ("/api/",)


class ApiKeyMiddleware:
    """Django middleware that authenticates requests via API key Bearer token.

    Runs on every request but only enforces authentication on ``/api/`` paths.
    On non-API paths, invalid/missing keys are silently ignored so that
    browser users with stale tokens in localStorage are not locked out.

    Attributes set on ``request`` for downstream views:
        ``api_user`` (dict | None): ``{"userId": "...", "scopes": [...]}``
        ``api_user_id`` (str | None): Shortcut to the user's UUID.
        ``api_key_scopes`` (list[str]): Scopes granted by the key.
        ``is_api_authenticated`` (bool): ``True`` if a valid key was found.
    """

    def __init__(self, get_response: Any) -> None:
        """Store the next middleware/view in the chain.

        Args:
            get_response: The next callable in Django's middleware chain.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request: extract, validate, and annotate the API key.

        The method follows a three-step flow:
        1. Initialize all API attributes to unauthenticated defaults.
        2. If an ``Authorization`` header is present, extract and validate
           the Bearer token.
        3. On success, annotate the request with user/scope data; on
           failure, return 401 only for protected ``/api/`` paths.

        Args:
            request: The incoming HTTP request.

        Returns:
            The response from the downstream view, or a 401 JSON error
            if authentication fails on a protected path.
        """
        # Always initialize API attributes so views can safely check them
        request.api_user = None
        request.api_user_id = None
        request.api_key_scopes: list[str] = []
        request.is_api_authenticated = False

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return self.get_response(request)

        token = _extract_bearer_token(auth_header)
        if token is None:
            # Malformed header (not "Bearer <token>") -- reject only on /api/ paths
            if _is_protected_path(request.path):
                return _unauthorized("Malformed Authorization header.")
            return self.get_response(request)

        result = _safe_validate(token)
        if result is None:
            # Token is syntactically valid but failed SHA-256 lookup
            if _is_protected_path(request.path):
                return _unauthorized("Invalid API key.")
            return self.get_response(request)

        # Valid key: annotate the request for downstream views
        request.api_user = {
            "userId": result["userId"],
            "scopes": result["scopes"],
        }
        request.api_user_id = result["userId"]
        request.api_key_scopes = result["scopes"]
        request.is_api_authenticated = True

        return self.get_response(request)


def _extract_bearer_token(header: str) -> str | None:
    """Extract the Bearer token from an Authorization header value.

    Returns the token string if the header is well-formed (``Bearer <token>``),
    or ``None`` for missing/malformed headers. The empty string is returned as
    ``None`` because an empty Bearer is not useful.
    """
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token if token else None


def _is_protected_path(path: str) -> bool:
    """Return ``True`` for API paths that require key rejection on failure."""
    return any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES)


def _safe_validate(token: str) -> dict[str, Any] | None:
    """Call :func:`validate_api_key`, catching unexpected errors."""
    try:
        return validate_api_key(token)
    except Exception:
        logger.warning(
            "API key validation failed unexpectedly for prefix %s…",
            token[:8] if len(token) >= 8 else "???",
            exc_info=True,
        )
        return None


def _unauthorized(detail: str) -> JsonResponse:
    """Return a ``401`` JSON response compatible with CLI/MCP consumers."""
    return JsonResponse({"error": detail}, status=401)


class QueryTimingMiddleware:
    """Capture per-request DB query timings and surface them via Server-Timing.

    Wraps every request to (a) reset the per-thread query log maintained by
    :mod:`core.mantecato_core.database`, (b) compute total wall-clock time,
    and (c) emit a ``Server-Timing`` response header listing the slowest
    queries.  The header is only added when :setting:`DEBUG` is enabled so
    that production responses stay lean and do not leak internal labels.

    The middleware also writes a one-line summary to ``logger.info`` whenever
    the request makes at least one DB query: ``"<path> N queries Tms (slow:
    <label> Xms)"``.  This gives operators a quick overview of which views
    are query-heavy without needing browser DevTools.

    Server-Timing format example:

    ``db_total;dur=412.7, sources.get_top_referrers;dur=180.4, ...``

    Browsers expose this in the Network panel under "Server Timing", making
    per-query latency visible without log scraping.
    """

    # Maximum number of individual query entries to emit in the header so
    # that the response size does not balloon when a view runs dozens of
    # short queries.  Slowest entries are kept; the rest are summarised.
    _MAX_HEADER_ENTRIES = 8

    def __init__(self, get_response: Any) -> None:
        """Store the next callable in the middleware chain."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Time the request, collect query stats, and append Server-Timing."""
        from django.conf import settings

        from core.mantecato_core.database import get_query_log, reset_query_log

        reset_query_log()
        started = _now_ms()
        response = self.get_response(request)
        total_ms = _now_ms() - started

        entries = get_query_log()
        if entries and logger.isEnabledFor(logging.INFO):
            slowest_label, slowest_ms = max(entries, key=lambda e: e[1])
            logger.info(
                "%s %d queries %.1fms (slowest: %s %.1fms)",
                request.path,
                len(entries),
                total_ms,
                slowest_label,
                slowest_ms,
            )

        if getattr(settings, "DEBUG", False):
            response["Server-Timing"] = _build_server_timing(
                total_ms, entries, self._MAX_HEADER_ENTRIES
            )

        return response


def _now_ms() -> float:
    """Return a monotonic timestamp in milliseconds.

    Uses :func:`time.perf_counter` for the same resolution as the per-query
    timer in :mod:`core.mantecato_core.database`, so the totals reported in
    the ``Server-Timing`` header are consistent with the individual entries.
    """
    import time

    return time.perf_counter() * 1000.0


def _build_server_timing(
    total_ms: float, entries: list[tuple[str, float]], max_entries: int
) -> str:
    """Format a list of timing entries as a Server-Timing header value.

    Keeps the slowest ``max_entries`` individual queries to bound header
    length, and adds a ``db_total`` aggregate covering every query (not
    just the ones shown).  The format complies with the
    `Server-Timing spec <https://w3c.github.io/server-timing/>`_: comma-
    separated metrics, each ``name;dur=<ms>`` and optionally
    ``;desc="..."``.

    Args:
        total_ms: Wall-clock time of the entire request in milliseconds.
        entries: Per-query log produced by :func:`get_query_log`.
        max_entries: Cap on the number of per-query metrics in the header.
    """
    db_total = sum(d for _, d in entries)
    metrics = [
        f"request;dur={total_ms:.1f}",
        f'db_total;dur={db_total:.1f};desc="{len(entries)} queries"',
    ]
    # Pick the slowest N entries so the most actionable ones are visible.
    top = sorted(entries, key=lambda e: e[1], reverse=True)[:max_entries]
    for label, duration in top:
        # ``label`` is already in the safe ``module.function`` form returned
        # by ``_caller_label``; no further sanitisation needed.
        metrics.append(f"{label};dur={duration:.1f}")
    return ", ".join(metrics)
