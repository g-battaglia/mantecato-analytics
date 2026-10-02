"""Unconfigured remote access must not load a transport or block ASGI startup."""

import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "not-an-origin",
        "http://analytics.example.test",
        "http://127.0.0.1:8000",
        "https://analytics.example.test/path",
        "https://analytics.example.test?query=1",
        "https://127.0.0.1",
    ],
)
def test_unconfigured_asgi_skips_transport_and_completes_lifespan(settings, origin):
    settings.DEBUG = False
    settings.MANTECATO_PUBLIC_URL = origin
    from mantecato.asgi import create_application

    with patch("apps.ai_connections.transport.create_transport") as transport:
        app = create_application()
    transport.assert_not_called()
    messages = []

    async def run():
        events = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

        async def receive():
            return next(events)

        async def send(message):
            messages.append(message)

        await app({"type": "lifespan"}, receive, send)
        await app(
            {"type": "http", "path": "/mcp", "scheme": "https", "http_version": "1.1"},
            receive,
            send,
        )

    asyncio.run(run())
    assert messages[:2] == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]
    assert messages[2]["status"] == 404
    assert (b"cache-control", b"no-store") in messages[2]["headers"]
    assert messages[3]["body"] == b'{"error": "ai_access_unavailable"}'
