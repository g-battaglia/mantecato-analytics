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
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "scheme": "https",
                "http_version": "1.1",
            },
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


@pytest.mark.parametrize(
    "scheme,proxy_header,headers,expected_status",
    [
        ("http", None, [(b"x-forwarded-proto", b"https")], 404),
        ("http", ("HTTP_X_FORWARDED_PROTO", "https"), [], 404),
        ("http", ("HTTP_X_FORWARDED_PROTO", "https"), [(b"x-forwarded-proto", b"http")], 404),
        ("http", ("HTTP_X_FORWARDED_PROTO", "https"), [(b"x-forwarded-proto", b"https")], 204),
        ("https", None, [], 204),
    ],
    ids=["proxy-disabled", "missing-header", "plain-http", "proxy-https", "direct-https"],
)
def test_mcp_uses_django_https_configuration(
    settings, scheme, proxy_header, headers, expected_status
):
    settings.DEBUG = False
    settings.MANTECATO_PUBLIC_URL = "https://analytics.example.test"
    settings.SECURE_PROXY_SSL_HEADER = proxy_header
    from mantecato.asgi import create_application

    received = []
    messages = []

    async def remote(scope, receive, send):
        received.append(scope)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    with patch("apps.ai_connections.transport.create_transport", return_value=(None, remote)):
        app = create_application()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "scheme": scheme,
        "headers": headers,
        "client": ("100.64.0.99", 1234),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == expected_status
    if expected_status == 204:
        assert received == [{**scope, "scheme": "https"}]
    else:
        assert received == []
    assert scope["scheme"] == scheme


def test_mcp_scheme_normalization_leaves_django_scope_unchanged(settings):
    settings.DEBUG = False
    settings.MANTECATO_PUBLIC_URL = ""
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    from mantecato.asgi import create_application

    received = []

    async def django_app(scope, receive, send):
        received.append(scope)

    with patch("mantecato.asgi.get_asgi_application", return_value=django_app):
        app = create_application()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health/",
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"https")],
    }
    asyncio.run(app(scope, None, None))
    assert received == [scope]
    assert received[0]["scheme"] == "http"
