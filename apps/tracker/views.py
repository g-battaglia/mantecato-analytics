"""Tracker endpoints — ``POST /api/send`` (ingestion) and ``GET /api/script``.

The ingestion endpoint accepts the Umami-compatible wire protocol from
``@mantecato/tracker`` and forwards into the analytics tables via
:mod:`apps.tracker.services`. The script endpoint serves the compiled
JavaScript tracker bundle.

Both endpoints are :class:`~django.views.View` subclasses so they share a
small ``_add_cors`` helper for the cross-origin headers that browser
trackers require.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.tracker.geo import resolve_geo
from apps.tracker.ip import get_client_ip
from apps.tracker.services import ingest_event, ingest_identify
from apps.tracker.session import resolve_session
from apps.tracker.ua import parse_user_agent

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

# Headers the tracker JS needs to send cross-origin. The session token
# header and the Umami-compatible cache header must both be allowed.
_CORS_ALLOW_HEADERS = "Content-Type, x-mantecato-session, x-umami-cache"


def _add_cors(response: HttpResponse) -> HttpResponse:
    """Stamp the cross-origin headers the tracker UMD bundle relies on.

    Adds permissive CORS headers (``Access-Control-Allow-Origin: *``) because
    the tracker script runs on customer domains that are different from the
    Mantecato host. The wildcard is intentional -- the ingestion endpoint is
    a public write-only API that does not expose sensitive data.

    Args:
        response: The HTTP response to add CORS headers to.

    Returns:
        The same response object, with CORS headers added (mutated in place).
    """
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
    return response


@method_decorator(csrf_exempt, name="dispatch")
class IngestView(View):
    """``POST /api/send`` — tracker event/identify ingestion endpoint.

    The wire format matches Umami, so the @mantecato/tracker and
    @mantecato/tracker-react packages can talk to either backend:

    .. code-block:: json

        {"type": "event", "payload": {"website": "<uuid>", "url": "/path", ...}}
        {"type": "identify", "payload": {"website": "<uuid>", "id": "<distinct>"}}

    Validation is intentionally minimal — the tracker is a hot path, and
    we already trust the website-id existence in :func:`resolve_session`.
    """

    http_method_names = ("post", "options")

    def options(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Handle CORS preflight requests with a 24-hour cache.

        Returns a 204 No Content with the necessary CORS headers to allow
        cross-origin POST requests from the tracker JavaScript. The 24-hour
        ``Access-Control-Max-Age`` avoids preflight on every page load.

        Args:
            request: The incoming OPTIONS request.

        Returns:
            A 204 response with CORS headers.
        """
        response = HttpResponse(status=204)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
        response["Access-Control-Max-Age"] = "86400"
        return response

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Process an incoming tracker event or identify call.

        This is the hot path of the analytics pipeline. Each page load or
        custom event from the tracker JS hits this endpoint. The processing
        steps are:

        1. Parse and validate the JSON body.
        2. Extract the client IP, User-Agent, device info, and geo location.
        3. Resolve (or create) the session and visit using the session token.
        4. Route to :func:`ingest_event` or :func:`ingest_identify` based on
           the message ``type``.
        5. Return the signed session token in ``{"cache": "<token>"}`` so the
           tracker JS can send it back on the next request.

        Args:
            request: The incoming POST request with the tracker payload.

        Returns:
            200 JSON with ``{"cache": "<signed_session_token>"}`` on success.
            400 JSON with ``{"error": "..."}`` for malformed requests.
        """
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        payload = body.get("payload")
        if not isinstance(payload, dict):
            return JsonResponse({"error": "Missing payload"}, status=400)

        website_id = payload.get("website")
        if not website_id:
            return JsonResponse({"error": "Missing website ID"}, status=400)

        # Extract client context: IP for fingerprinting/geo, UA for device info
        ip = get_client_ip(request)
        ua_string = request.META.get("HTTP_USER_AGENT", "")
        device_info = parse_user_agent(ua_string)
        geo_info = resolve_geo(request, ip)

        # Check for an existing session token in the request headers.
        # Supports both the Mantecato header and the Umami-compatible fallback.
        session_header = request.META.get("HTTP_X_MANTECATO_SESSION") or request.META.get(
            "HTTP_X_UMAMI_CACHE"
        )

        # Resolve session and visit IDs (either from token or fresh fingerprint)
        session_id, visit_id, token = resolve_session(
            website_id=website_id,
            ip=ip,
            ua=ua_string,
            screen=payload.get("screen", ""),
            language=payload.get("language", ""),
            session_header=session_header,
            device_info=device_info,
            geo_info=geo_info,
        )

        # Route to the appropriate ingestion handler based on message type
        msg_type = body.get("type")
        if msg_type == "event":
            ingest_event(
                website_id=website_id,
                session_id=session_id,
                visit_id=visit_id,
                payload=payload,
                device_info=device_info,
                geo_info=geo_info,
            )
        elif msg_type == "identify":
            ingest_identify(website_id=website_id, session_id=session_id, payload=payload)
        # Unknown ``type`` values are silently ignored -- matches Umami's
        # behaviour and the historical contract used by the JS tracker.

        return _add_cors(JsonResponse({"cache": token}))


# ----------------------------------------------------------------------------
# Tracker script bundle — cached in-process on first read.
# ----------------------------------------------------------------------------


_SCRIPT_CACHE: bytes | None = None


@require_GET
def api_script(request: HttpRequest) -> HttpResponse:
    """``GET /api/script`` — return the compiled tracker JavaScript bundle.

    The bundle is read from disk once and cached in process memory. Missing
    file → ``404`` with a placeholder body so the network call still
    succeeds (clients fail open).
    """
    global _SCRIPT_CACHE  # noqa: PLW0603  process-local cache, intentional
    if _SCRIPT_CACHE is None:
        script_path = (
            Path(__file__).resolve().parent.parent.parent
            / "packages"
            / "tracker"
            / "dist"
            / "script.js"
        )
        try:
            _SCRIPT_CACHE = script_path.read_bytes()
        except FileNotFoundError:
            return HttpResponse(
                "// tracker not built",
                content_type="application/javascript",
                status=404,
            )
    response = HttpResponse(_SCRIPT_CACHE, content_type="application/javascript")
    response["Cache-Control"] = "public, max-age=86400"
    response["Access-Control-Allow-Origin"] = "*"
    return response


# Backward-compatible re-export so existing URL configs / tests that
# import ``api_send`` keep resolving.
api_send = IngestView.as_view()
