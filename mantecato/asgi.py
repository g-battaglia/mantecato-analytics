"""Django and the official MCP SDK share one bounded ASGI web service."""

import os
from io import BytesIO

from asgiref.sync import ThreadSensitiveContext, sync_to_async
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.core.handlers.asgi import ASGIRequest
from django.db import connections
from django.http import JsonResponse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mantecato.settings")


def create_application():
    # Per-request ASGI thread contexts must not retain database sockets, even
    # if a legacy WSGI operator configured persistent connections explicitly.
    for database in settings.DATABASES.values():
        database["CONN_MAX_AGE"] = 0
    django_app = get_asgi_application()
    if settings.DEBUG:
        from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

        django_app = ASGIStaticFilesHandler(django_app)
    from apps.ai_connections.policy import AccessDenied, public_origin

    remote = None
    try:
        public_origin()
        from apps.ai_connections.transport import create_transport

        _, remote = create_transport()
    except AccessDenied:
        # Unconfigured AI access must never stop collection/health or load the SDK.
        pass

    async def application(scope, receive, send):
        if scope["type"] == "http" and scope.get("http_version", "1.1") in ("1.0", "1.1"):
            original_send = send

            async def closing_send(message):
                if message["type"] == "http.response.start":
                    headers = [
                        (k, v) for k, v in message.get("headers", []) if k.lower() != b"connection"
                    ]
                    message = {**message, "headers": headers + [(b"connection", b"close")]}
                await original_send(message)

            # Gunicorn 26 keep-alive=0 closes sockets but does not advertise
            # that closure. Explicit HTTP/1 signalling prevents client reuse
            # races and dropped concurrent requests. Never send this on HTTP/2.
            send = closing_send
        if scope["type"] == "lifespan":
            if remote:
                return await remote(scope, receive, send)
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope.get("path") == "/mcp":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            # Share Django's HTTPS/proxy configuration with the MCP transport.
            scope = {**scope, "scheme": ASGIRequest(scope, BytesIO()).scheme}
            insecure = not settings.DEBUG and scope.get("scheme") != "https"
            if remote is None or insecure:
                response = JsonResponse({"error": "ai_access_unavailable"}, status=404)
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": response.content})
                return

            async def private_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers += [
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                    message = {**message, "headers": headers}
                await send(message)

            return await remote(scope, receive, private_send)
        # Native-worker disconnect/cancellation may precede Django's response
        # close signal. Own the reentrant thread context so all ORM sockets
        # close even on that path, before its executor is discarded.
        async with ThreadSensitiveContext():
            try:
                return await django_app(scope, receive, send)
            finally:
                await sync_to_async(connections.close_all, thread_sensitive=True)()

    return application


application = create_application()
