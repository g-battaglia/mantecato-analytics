"""Overload responses preserve browser UX, protocol JSON and MCP CORS policy."""

import asyncio
from unittest.mock import patch

import pytest

from mantecato.admission import unavailable


@pytest.mark.parametrize(
    "path,accept,hx,html",
    [
        ("/", "text/html,application/xhtml+xml", False, True),
        ("/pages/", "text/html", False, True),
        ("/sections/", "text/html;q=0.5", False, True),
        ("/dashboards/example/", "text/html", False, True),
        ("/", "text/html;q=0, application/json", False, False),
        ("/", "text/html;q=invalid", False, False),
        ("/", "application/json", False, False),
        ("/overview/tab/", "text/html", True, False),
        ("/api/v1/analytics/query/", "text/html", False, False),
        ("/mcp", "text/html", False, False),
    ],
)
def test_browser_html_is_not_returned_to_htmx_or_protocol_clients(path, accept, hx, html):
    messages = []

    async def send(message):
        messages.append(message)

    headers = [(b"accept", accept.encode())]
    if hx:
        headers.append((b"hx-request", b"true"))
    scope = {"type": "http", "path": path, "method": "GET", "headers": headers}
    asyncio.run(unavailable(scope, send))
    response, body = messages
    headers = dict(response["headers"])
    assert response["status"] == 503
    assert headers[b"cache-control"] == b"private, no-store"
    assert headers[b"retry-after"] == b"1"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert int(headers[b"content-length"]) == len(body["body"])
    if html:
        assert headers[b"content-type"] == b"text/html; charset=utf-8"
        assert b'<a href="">Retry</a>' in body["body"]
    else:
        assert headers[b"content-type"] == b"application/json"
        assert body["body"] == b'{"error":"analytics_busy"}'


@pytest.mark.parametrize(
    "origin",
    [
        "https://claude.ai",
        "https://analytics.example.test",
        "https://browser.example.test",
        "https://untrusted.example.test",
        None,
    ],
)
def test_saturated_mcp_has_the_same_cors_allowlist_and_exposes_retry_after(settings, origin):
    settings.DEBUG = False
    settings.MANTECATO_PUBLIC_URL = "https://analytics.example.test"
    settings.AI_MCP_ALLOWED_ORIGINS = ["https://browser.example.test"]
    settings.ANALYTICS_MAX_CONCURRENT = 1
    settings.ANALYTICS_MAX_WAITING = 0
    from mantecato.asgi import create_application

    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        messages = []

        async def django(scope, receive, send):
            calls.append("django")
            started.set()
            await release.wait()

        async def remote(scope, receive, send):
            calls.append("remote")

        async def send(message):
            messages.append(message)

        with (
            patch("mantecato.asgi.get_asgi_application", return_value=django),
            patch("apps.ai_connections.transport.create_transport", return_value=(None, remote)),
        ):
            app = create_application()
        task = asyncio.create_task(
            app({"type": "http", "path": "/pages/", "method": "GET"}, None, send)
        )
        await started.wait()
        try:
            await app(
                {
                    "type": "http",
                    "path": "/mcp",
                    "method": "POST",
                    "scheme": "https",
                    "headers": [(b"origin", origin.encode())] if origin else [],
                },
                None,
                send,
            )
            assert calls == ["django"]  # Rejection creates no MCP/ORM work.
            assert messages[0]["status"] == 503
            headers = dict(messages[0]["headers"])
            assert headers[b"retry-after"] == b"1"
            assert headers[b"referrer-policy"] == b"no-referrer"
            assert headers[b"cache-control"] == b"private, no-store"
            assert (
                b"retry-after" in headers.get(b"access-control-expose-headers", b"").lower()
                or origin is None
            )
            if origin and origin != "https://untrusted.example.test":
                assert headers[b"access-control-allow-origin"] == origin.encode()
            else:
                assert b"access-control-allow-origin" not in headers
            assert messages[1]["body"] == b'{"error":"analytics_busy"}'
        finally:
            release.set()
            await task

    asyncio.run(run())


def test_unconfigured_mcp_remains_unavailable_even_when_analytics_is_saturated(settings):
    settings.MANTECATO_PUBLIC_URL = ""
    settings.ANALYTICS_MAX_CONCURRENT = 1
    settings.ANALYTICS_MAX_WAITING = 0
    from mantecato.asgi import create_application

    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def django(scope, receive, send):
            started.set()
            await release.wait()

        messages = []

        async def send(message):
            messages.append(message)

        with patch("mantecato.asgi.get_asgi_application", return_value=django):
            app = create_application()
        task = asyncio.create_task(
            app({"type": "http", "path": "/pages/", "method": "GET"}, None, send)
        )
        await started.wait()
        try:
            await app(
                {"type": "http", "path": "/mcp", "method": "POST", "scheme": "https"}, None, send
            )
            assert messages[0]["status"] == 404
        finally:
            release.set()
            await task

    asyncio.run(run())
