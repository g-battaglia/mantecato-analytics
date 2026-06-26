"""Tracker endpoints — ``POST /api/send`` (pageview ingestion) and ``GET /api/script``.

The ingestion endpoint accepts a minimal, privacy-first payload from the
tracker JavaScript and records an anonymous pageview. No cookies, tokens,
session identifiers, or persistent tracking of any kind are used.

Both endpoints are :class:`~django.views.View` subclasses so they share a
small ``_add_cors`` helper for the cross-origin headers that browser
trackers require.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.analytics.formatting import format_compact
from apps.tracker.geo import resolve_geo
from apps.tracker.ip import get_client_ip
from apps.tracker.services import (
    ingest_custom_event,
    ingest_engagement,
    ingest_pageview,
    is_trackable_website,
)
from apps.tracker.ua import classify_bot_user_agent, parse_user_agent
from core.mantecato_core.badge import render_badge
from core.mantecato_core.database import raw_query_one
from core.mantecato_core.ip_reputation import is_datacenter_ip

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

# Headers the tracker JS needs to send cross-origin.
_CORS_ALLOW_HEADERS = "Content-Type"

# Best-effort per-process per-IP rate-limit state (fixed 60s window). Keyed on
# the extracted client IP; bounded to avoid unbounded memory under spoofed IPs.
_RATE_WINDOW_S = 60
_RATE_STATE_MAX = 10_000
_rate_state: dict[str, tuple[int, float]] = {}
_rate_lock = threading.Lock()


def _add_cors(response: HttpResponse) -> HttpResponse:
    """Stamp the cross-origin headers the tracker bundle relies on.

    Adds permissive CORS headers because the tracker script runs on
    customer domains different from the Mantecato host. The ingestion
    endpoint is a public write-only API that does not expose sensitive data.
    """
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
    return response


def _content_length(request: HttpRequest) -> int:
    """Return the declared request body size in bytes (0 if absent/invalid)."""
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        return 0


def _privacy_opt_out(request: HttpRequest) -> bool:
    """Return ``True`` when the request signals a privacy opt-out to honour.

    Enforced server-side so the guarantee holds even for clients that bypass
    the browser tracker's own GPC/DNT check (curl, forks, server SDKs).
    """
    if getattr(settings, "RESPECT_GPC", True) and request.META.get("HTTP_SEC_GPC") == "1":
        return True
    return bool(getattr(settings, "RESPECT_DNT", False) and request.META.get("HTTP_DNT") == "1")


def _rate_limited(ip: str) -> bool:
    """Best-effort per-process, per-IP fixed-window rate check.

    Returns ``True`` when *ip* has exceeded ``INGEST_RATE_LIMIT_PER_MINUTE`` in
    the current window. Disabled (always ``False``) when the limit is 0. The
    state is per gunicorn worker, so this only meaningfully throttles once the
    client IP is extracted correctly (see ``TRUSTED_PROXY_COUNT``).
    """
    limit = getattr(settings, "INGEST_RATE_LIMIT_PER_MINUTE", 0)
    if limit <= 0 or not ip:
        return False
    now = time.monotonic()
    with _rate_lock:
        count, start = _rate_state.get(ip, (0, now))
        if now - start >= _RATE_WINDOW_S:
            count, start = 0, now
        count += 1
        _rate_state[ip] = (count, start)
        if len(_rate_state) > _RATE_STATE_MAX:
            # First drop entries whose window has fully elapsed.
            stale = [k for k, (_, s) in _rate_state.items() if now - s >= _RATE_WINDOW_S]
            for k in stale:
                del _rate_state[k]
            # If still over the cap (high-cardinality flood of still-active IPs),
            # hard-reset to bound memory — acceptable for a best-effort limiter.
            if len(_rate_state) > _RATE_STATE_MAX:
                _rate_state.clear()
                _rate_state[ip] = (count, start)
        return count > limit


@method_decorator(csrf_exempt, name="dispatch")
class IngestView(View):
    """``POST /api/send`` — anonymous pageview ingestion endpoint.

    The wire format is intentionally minimal for privacy-first operation:

    .. code-block:: json

        {"type": "event", "payload": {"website": "<uuid>", "url": "/path", "title": "Page"}}

    Only pageviews are recorded. No session tokens are issued or accepted.
    Custom events may include a name only. No referrer, UTM, click ID,
    event payload/properties, or identify data is processed.

    Validation is intentionally minimal — the tracker is a hot path.
    """

    http_method_names = ("post", "options")

    def options(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Handle CORS preflight requests with a 24-hour cache."""
        response = HttpResponse(status=204)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = _CORS_ALLOW_HEADERS
        response["Access-Control-Max-Age"] = "86400"
        return response

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Process an incoming anonymous pageview.

        Steps:
        1. Parse and validate the JSON body.
        2. Extract device info from User-Agent (for aggregate breakdowns + bot detection).
        3. Resolve geo from IP (country-level only).
        4. Insert an anonymous pageview row.
        5. Return a simple OK response (no tokens).

        Args:
            request: The incoming POST request with the tracker payload.

        Returns:
            200 JSON with ``{"ok": true}`` on success.
            400 JSON with ``{"error": "..."}`` for malformed requests.
        """
        # Reject oversized bodies before materialising request.body — this is an
        # unauthenticated public endpoint and legitimate payloads are tiny.
        max_body = getattr(settings, "INGEST_MAX_BODY_BYTES", 16384)
        if max_body and _content_length(request) > max_body:
            return _add_cors(JsonResponse({"error": "Payload too large"}, status=413))

        try:
            raw = request.body
        except Exception:  # noqa: BLE001  RequestDataTooBig etc. → treat as too large
            return _add_cors(JsonResponse({"error": "Payload too large"}, status=413))
        if max_body and len(raw) > max_body:
            return _add_cors(JsonResponse({"error": "Payload too large"}, status=413))

        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        payload = body.get("payload")
        if not isinstance(payload, dict):
            return JsonResponse({"error": "Missing payload"}, status=400)

        website_id = payload.get("website")
        if not website_id:
            return JsonResponse({"error": "Missing website ID"}, status=400)

        # Process pageviews/custom events and engagement beacons; ignore the rest.
        msg_type = body.get("type")
        if msg_type not in ("event", "engagement"):
            return _add_cors(JsonResponse({"ok": True}))

        # Honour server-side privacy opt-out (GPC/DNT) before doing any work.
        if _privacy_opt_out(request):
            return _add_cors(JsonResponse({"ok": True}))

        # Silently drop events for unknown/inactive websites: prevents poisoning
        # arbitrary site UUIDs and unbounded storage growth. 200 (not 4xx) avoids
        # leaking which website ids exist.
        if not is_trackable_website(website_id):
            return _add_cors(JsonResponse({"ok": True}))

        ip = get_client_ip(request)

        # Best-effort per-IP flood protection on the public endpoint.
        if _rate_limited(ip):
            return _add_cors(JsonResponse({"error": "Too many requests"}, status=429))

        ua_string = request.META.get("HTTP_USER_AGENT", "")
        is_bot, bot_reason = classify_bot_user_agent(ua_string)
        # Flag cloud/datacenter source IPs as bots (IP used transiently, never stored).
        if not is_bot and settings.DETECT_DATACENTER_IPS and is_datacenter_ip(ip):
            is_bot, bot_reason = True, "datacenter_ip"

        # Engagement heartbeats only fold active time into the open visit; they
        # write no event row and need no device/geo resolution.
        if msg_type == "engagement":
            ingest_engagement(
                website_id=website_id,
                payload=payload,
                is_bot=is_bot,
                ip=ip,
                user_agent=ua_string,
            )
            return _add_cors(JsonResponse({"ok": True}))

        device_info = parse_user_agent(ua_string)
        country = resolve_geo(request, ip)

        event_name = payload.get("name")
        if isinstance(event_name, str) and event_name.strip():
            ingest_custom_event(
                website_id=website_id,
                event_name=event_name,
                payload=payload,
                device_info=device_info,
                country=country,
                is_bot=is_bot,
                bot_reason=bot_reason,
                ip=ip,
                user_agent=ua_string,
            )
        else:
            ingest_pageview(
                website_id=website_id,
                payload=payload,
                device_info=device_info,
                country=country,
                is_bot=is_bot,
                bot_reason=bot_reason,
                ip=ip,
                user_agent=ua_string,
            )

        return _add_cors(JsonResponse({"ok": True}))


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


# ----------------------------------------------------------------------------
# First-party README view-counter badge — GET /api/badge
# ----------------------------------------------------------------------------
#
# Serves an SVG counter badge so a repo README needs no third-party badge
# service. It counts its OWN fetches (≈ README renders, made server-side by
# GitHub's camo proxy — no end-user device, so no ePrivacy Art. 5(3) trigger)
# into a single aggregate integer per site. No IP/User-Agent/per-person data is
# stored, and the fetch never enters the pageview pipeline. The counter is keyed
# on an existing site's public ``share_id`` (operator opt-in), so the key set is
# bounded — no arbitrary counters. NOTE: GitHub caches the image (camo), so the
# count under-reports and is not real-time — inherent to every such badge.


def _badge_response(svg: str, *, status: int = 200) -> HttpResponse:
    """Wrap an SVG string in an image response with no-cache + CORS headers."""
    response = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8", status=status)
    # Discourage caching so GitHub's camo proxy re-fetches (best-effort; camo
    # still caches, which is why the counter under-reports).
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return _add_cors(response)


def _bump_badge_hit(website_id: str) -> int:
    """Atomically increment and return the badge counter for *website_id*.

    A single UPSERT (concurrency-safe, one round-trip) avoids the get-or-create
    race; ``RETURNING`` gives the new value.
    """
    row = raw_query_one(
        """
        INSERT INTO badge_hit (id, website_id, count, updated_at)
        VALUES ({{id::uuid}}, {{wid::uuid}}, 1, now())
        ON CONFLICT (website_id)
            DO UPDATE SET count = badge_hit.count + 1, updated_at = now()
        RETURNING count
        """,
        {"id": str(uuid.uuid4()), "wid": website_id},
    )
    return int(row["count"]) if row else 0


@require_GET
def badge_view(request: HttpRequest) -> HttpResponse:
    """``GET /api/badge?share_id=<id>`` — first-party README view-counter badge.

    Resolves the site by its public ``share_id``, atomically increments that
    site's badge counter, and returns a flat SVG ``[ label | N ]``. Unknown or
    missing ``share_id`` returns a 404 *image* (so a README never shows a broken
    image). Optional ``label`` (default ``views``) and ``color`` query params.
    """
    share_id = (request.GET.get("share_id") or "").strip()
    label = (request.GET.get("label") or "views").strip() or "views"
    color = request.GET.get("color")

    if not share_id:
        return _badge_response(render_badge("badge", "no share_id", "red"), status=404)

    from apps.core.models import Website

    website_id = (
        Website.objects.filter(share_id=share_id, is_deleted=False)
        .values_list("id", flat=True)
        .first()
    )
    if website_id is None:
        return _badge_response(render_badge(label, "not found", "red"), status=404)

    count = _bump_badge_hit(str(website_id))
    return _badge_response(render_badge(label, format_compact(count), color))


# Backward-compatible re-export so existing URL configs / tests that
# import ``api_send`` keep resolving.
api_send = IngestView.as_view()
