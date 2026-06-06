"""Tracker ingestion services — anonymous aggregate pageview recording.

This module is the write-path core of the analytics pipeline. It receives
validated payloads from :mod:`apps.tracker.views` and inserts rows into the
``website_event`` table using raw SQL via :func:`core.mantecato_core.database.raw_query`.

Privacy-first design (per PLAN.md):
- No session_id or visit_id — every pageview is independent and anonymous.
- No referrer tracking, UTM params, or click IDs.
- No custom event payloads, identify calls, revenue tracking, or session data.
- Only the minimal data needed for aggregate pageview analytics is stored:
  url_path, url_query, page_title, hostname, and device/browser/geo metadata
  for aggregate breakdowns and bot detection.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from django.utils import timezone

from core.mantecato_core.database import raw_query


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
) -> None:
    """Insert an anonymous pageview event.

    Every pageview is an independent, anonymous event. Only aggregate-level
    data is stored: URL, title, hostname, device classification, and country.
    """
    event_id = str(uuid.uuid4())
    now = timezone.now()

    url_info = _parse_url(payload.get("url", ""))

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, created_at,
             url_path, url_query,
             page_title, event_type, hostname,
             browser, os, device,
             country)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}},
             {{pageTitle}}, 1, {{hostname}},
             {{browser}}, {{os}}, {{device}},
             {{country}})
        """,
        {
            "eventId": event_id,
            "websiteId": website_id,
            "createdAt": now,
            "urlPath": url_info["url_path"],
            "urlQuery": url_info["url_query"],
            "pageTitle": unquote(payload.get("title") or "")[:500] or None,
            "hostname": ((payload.get("hostname") or "").removeprefix("www."))[:100] or None,
            "browser": device_info.get("browser"),
            "os": device_info.get("os"),
            "device": device_info.get("device"),
            "country": country,
        },
    )
