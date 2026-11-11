"""Bound analytics concurrency before Django creates per-request ORM threads.

This is process-local, intentionally small and independent of the collector.
It bounds both running work and waiting ASGI tasks without Redis or a queue
service. No request bodies, principals or analytics results are retained here.
"""

from __future__ import annotations

import asyncio
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
        if concurrent < 1 or waiting < 0 or timeout <= 0:
            raise ValueError("Analytics admission limits must be positive (waiting may be zero)")
        self.concurrent = concurrent
        self.waiting_limit = waiting
        self.timeout = timeout
        self.running = 0
        self.waiters: set[asyncio.Future] = set()

    def _wake(self):
        # Wake all bounded waiters; only those with a free slot may enter.
        for waiter in self.waiters:
            if not waiter.done():
                waiter.set_result(None)

    @asynccontextmanager
    async def slot(self):
        """Yield admission status. Cancellation cannot leak a slot or waiter."""
        admitted = False
        if self.running < self.concurrent:
            self.running += 1
            admitted = True
        elif len(self.waiters) < self.waiting_limit:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.timeout
            try:
                async with asyncio.timeout_at(deadline):
                    while self.running >= self.concurrent:
                        waiter = loop.create_future()
                        self.waiters.add(waiter)
                        try:
                            await waiter
                        finally:
                            self.waiters.discard(waiter)
                    self.running += 1
                    admitted = True
            except TimeoutError:
                pass
        try:
            yield admitted
        finally:
            if admitted:
                self.running -= 1
                self._wake()


async def unavailable(scope, send):
    """Explicit retry response, never a successful ACK of a collector event."""
    headers = [
        (b"content-type", b"application/json"),
        (b"retry-after", b"1"),
        (b"cache-control", b"private, no-store"),
    ]
    if scope.get("http_version", "1.1") in ("1.0", "1.1"):
        headers.append((b"connection", b"close"))
    await send({"type": "http.response.start", "status": 503, "headers": headers})
    body = b"" if scope.get("method") == "HEAD" else b'{"error":"analytics_busy"}'
    await send({"type": "http.response.body", "body": body})
