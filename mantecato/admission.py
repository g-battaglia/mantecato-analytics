"""Bound analytics concurrency before Django creates per-request ORM threads.

This is process-local, intentionally small and independent of the collector.
It bounds both running work and waiting ASGI tasks without Redis or a queue
service. No request bodies, principals or analytics results are retained here.
"""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager

_ANALYTICS_PAGES = frozenset(
    {
        "/",
        "/pages/",
        "/entry/",
        "/sections/",
        "/events/",
        "/devices/",
        "/geo/",
        "/sources/",
        "/compare/",
        "/heatmap/",
        "/realtime/",
        "/filter-values/",
    }
)
_ANALYTICS_PREFIXES = (
    "/overview/",
    "/realtime/",
    "/api/analytics/",
    "/api/v1/",
    "/dashboards/",
)


def is_analytics(scope: dict) -> bool:
    """Keep collector, preflight, static, health and authentication outside."""
    if scope["type"] != "http" or scope.get("method") == "OPTIONS":
        return False
    path = scope.get("path", "")
    return path == "/mcp" or path in _ANALYTICS_PAGES or path.startswith(_ANALYTICS_PREFIXES)


class AnalyticsGate:
    def __init__(self, concurrent: int, waiting: int, timeout: float):
        if concurrent < 1 or waiting < 0 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Analytics admission limits must be positive (waiting may be zero)")
        self.concurrent = concurrent
        self.waiting_limit = waiting
        self.timeout = timeout
        self.running = 0
        self.waiting = 0
        # Semaphore reserves released slots for existing waiters. A new request
        # cannot barge ahead between release() and a waiter's resumption.
        self._slots = asyncio.Semaphore(concurrent)

    @asynccontextmanager
    async def slot(self):
        """Yield admission status. Cancellation cannot leak a slot or waiter."""
        admitted = False
        if not self._slots.locked() or self.waiting < self.waiting_limit:
            self.waiting += 1
            try:
                async with asyncio.timeout(self.timeout):
                    await self._slots.acquire()
                admitted = True
                self.running += 1
            except TimeoutError:
                pass
            finally:
                self.waiting -= 1
        try:
            yield admitted
        finally:
            if admitted:
                self.running -= 1
                self._slots.release()


def _html_navigation(scope):
    """Only full-page browser navigations get HTML; APIs/MCP/HTMX keep JSON."""
    path = scope.get("path", "")
    headers = {name.lower(): value for name, value in scope.get("headers", [])}
    if path == "/mcp" or path.startswith("/api/"):
        return False
    if headers.get(b"hx-request", b"").strip().lower() == b"true":
        return False
    for item in headers.get(b"accept", b"").decode("latin-1").split(","):
        media_type, *parameters = item.strip().lower().split(";")
        if media_type != "text/html":
            continue
        quality = "1"
        for parameter in parameters:
            name, _, value = parameter.strip().partition("=")
            if name == "q":
                quality = value
        try:
            if 0 < float(quality) <= 1:
                return True
        except ValueError:
            pass
    return False


async def unavailable(scope, send):
    """Retryable overload without an ORM thread or request-derived HTML content."""
    html = _html_navigation(scope)
    body = (
        b'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        b'<meta name="viewport" content="width=device-width, initial-scale=1">'
        b"<title>Analytics temporarily busy</title></head><body><main>"
        b"<h1>Analytics temporarily busy</h1><p>Please try again shortly.</p>"
        b'<a href="">Retry</a></main></body></html>'
        if html
        else b'{"error":"analytics_busy"}'
    )
    headers = [
        (b"content-type", b"text/html; charset=utf-8" if html else b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"retry-after", b"1"),
        (b"cache-control", b"private, no-store"),
        (b"referrer-policy", b"no-referrer"),
        (b"x-content-type-options", b"nosniff"),
    ]
    if scope.get("http_version", "1.1") in ("1.0", "1.1"):
        headers.append((b"connection", b"close"))
    await send({"type": "http.response.start", "status": 503, "headers": headers})
    await send(
        {"type": "http.response.body", "body": b"" if scope.get("method") == "HEAD" else body}
    )
