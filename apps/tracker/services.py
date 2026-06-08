"""Tracker ingestion services — anonymous aggregate pageview recording.

This module is the write-path core of the analytics pipeline. It receives
validated payloads from :mod:`apps.tracker.views` and inserts rows into the
``website_event`` table using raw SQL via :func:`core.mantecato_core.database.raw_query`.

Privacy-first design (per PLAN.md):
- No session_id or visit_id — every pageview is independent and anonymous.
- No referrer tracking, UTM params, or click IDs.
- Custom events store only the event name; no payload/properties.
- No identify calls, revenue tracking, or session data.
- Only the minimal data needed for aggregate pageview analytics is stored:
  url_path, url_query, page_title, event_name, hostname, and device/browser/geo
  metadata for aggregate breakdowns and bot detection.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from django.utils import timezone

from core.mantecato_core.database import raw_query
from core.mantecato_core.visitor_estimation import scope_rows_for_event, update_visitor_sketches


def _parse_url(url: str) -> dict[str, str | None]:
    """Parse a page URL into its path and query string components.

    Args:
        url: The raw page URL from the tracker payload (may be empty).

    Returns:
        A dict with ``url_path`` (always a non-empty string) and
        ``url_query`` (the query string without ``?``, or ``None``).
    """
    if not url:
        return {"url_path": "/", "url_query": None}
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path == "/undefined":
        path = "/"
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"
    path = unquote(path)
    query = parsed.query or None
    return {"url_path": path[:500], "url_query": query[:500] if query else None}


def ingest_pageview(
    website_id: str,
    payload: dict[str, Any],
    device_info: dict[str, str | None],
    country: str | None,
    is_bot: bool = False,
    bot_reason: str | None = None,
    ip: str | None = None,
) -> None:
    """Insert an anonymous pageview event.

    Every pageview is an independent, anonymous event. Only aggregate-level
    data is stored: URL, title, hostname, device classification, and country.
    """
    event_id = str(uuid.uuid4())
    now = timezone.now()

    url_info = _parse_url(payload.get("url", ""))
    url_path = url_info["url_path"]

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, created_at,
             url_path, url_query,
             page_title, event_type, event_name, hostname,
             browser, os, device,
             country, is_bot, bot_reason)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}},
             {{pageTitle}}, 1, NULL, {{hostname}},
             {{browser}}, {{os}}, {{device}},
             {{country}}, {{isBot}}, {{botReason}})
        """,
        {
            "eventId": event_id,
            "websiteId": website_id,
            "createdAt": now,
            "urlPath": url_path,
            "urlQuery": url_info["url_query"],
            "pageTitle": unquote(payload.get("title") or "")[:500] or None,
            "hostname": ((payload.get("hostname") or "").removeprefix("www."))[:100] or None,
            "browser": device_info.get("browser"),
            "os": device_info.get("os"),
            "device": device_info.get("device"),
            "country": country,
            "isBot": is_bot,
            "botReason": bot_reason[:80] if bot_reason else None,
        },
    )
    update_visitor_sketches(
        website_id=website_id,
        occurred_at=now,
        ip=ip,
        device_info=device_info,
        url_path=url_path,
        is_bot=is_bot,
    )


def ingest_custom_event(
    website_id: str,
    event_name: str,
    payload: dict[str, Any],
    device_info: dict[str, str | None],
    country: str | None,
    is_bot: bool = False,
    bot_reason: str | None = None,
    ip: str | None = None,
) -> None:
    """Insert an anonymous custom event count.

    Only the event name is stored. Arbitrary event properties are rejected by
    omission in the view layer and never persisted.
    """
    clean_name = str(event_name).strip()[:100]
    if not clean_name:
        return

    event_id = str(uuid.uuid4())
    now = timezone.now()
    url_info = _parse_url(payload.get("url", ""))
    url_path = url_info["url_path"]

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, created_at,
             url_path, url_query,
             page_title, event_type, event_name, hostname,
             browser, os, device,
             country, is_bot, bot_reason)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}},
             {{pageTitle}}, 2, {{eventName}}, {{hostname}},
             {{browser}}, {{os}}, {{device}},
             {{country}}, {{isBot}}, {{botReason}})
        """,
        {
            "eventId": event_id,
            "websiteId": website_id,
            "createdAt": now,
            "urlPath": url_path,
            "urlQuery": url_info["url_query"],
            "pageTitle": unquote(payload.get("title") or "")[:500] or None,
            "eventName": clean_name,
            "hostname": ((payload.get("hostname") or "").removeprefix("www."))[:100] or None,
            "browser": device_info.get("browser"),
            "os": device_info.get("os"),
            "device": device_info.get("device"),
            "country": country,
            "isBot": is_bot,
            "botReason": bot_reason[:80] if bot_reason else None,
        },
    )
    update_visitor_sketches(
        website_id=website_id,
        occurred_at=now,
        ip=ip,
        device_info=device_info,
        url_path=url_path,
        is_bot=is_bot,
        scopes=scope_rows_for_event(clean_name),
    )
