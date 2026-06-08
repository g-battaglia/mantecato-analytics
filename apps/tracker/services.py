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

import logging
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from django.utils import timezone

from core.mantecato_core.database import raw_query
from core.mantecato_core.visitor_counting import (
    record_scope_presence,
    record_visit,
    section_for_path,
    visitor_key_for,
)

logger = logging.getLogger(__name__)

# Throttle for the lazy, scheduler-free rollup piggybacked on ingestion.
_ROLLUP_MIN_INTERVAL_S = 3600
_last_rollup_attempt = None


def _maybe_rollup() -> None:
    """Best-effort, throttled discard of finished-day visitor state.

    Piggybacks the compute-and-discard rollup on the write path so it runs
    without a scheduler: at most once per hour per process, never blocking or
    breaking ingestion. A scheduled ``manage.py rollup_visitors`` is the
    deterministic backstop for the strict ≤24h discard guarantee.
    """
    global _last_rollup_attempt  # noqa: PLW0603  process-local throttle, intentional
    now = timezone.now()
    if (
        _last_rollup_attempt is not None
        and (now - _last_rollup_attempt).total_seconds() < _ROLLUP_MIN_INTERVAL_S
    ):
        return
    _last_rollup_attempt = now
    try:
        from core.mantecato_core.visitor_counting import (
            has_unrolled_past_periods,
            rollup_finished_periods,
        )

        if has_unrolled_past_periods():
            rollup_finished_periods()
    except Exception:
        logger.warning("Lazy visitor rollup failed; will retry later", exc_info=True)


def _parse_url(url: str) -> dict[str, str | None]:
    """Parse a page URL into its path component.

    The query string is intentionally **discarded and never stored**: it can
    carry personal data (``?email=``, ``?token=``, ``?name=``...) that has no
    place in privacy-first aggregate analytics. ``url_query`` is always ``None``.

    Args:
        url: The raw page URL from the tracker payload (may be empty).

    Returns:
        A dict with ``url_path`` (always a non-empty string) and ``url_query``
        (always ``None``).
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
    return {"url_path": path[:500], "url_query": None}


def ingest_pageview(
    website_id: str,
    payload: dict[str, Any],
    device_info: dict[str, str | None],
    country: str | None,
    is_bot: bool = False,
    bot_reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert an anonymous pageview event and fold it into exact visit counts.

    Only aggregate-level data is stored on the event row: URL, title, hostname,
    device classification, and country. The ``ip``/``user_agent`` are passed to
    :func:`record_visit` for exact, same-day visitor/visit counting and are
    never persisted (see :mod:`core.mantecato_core.visitor_counting`).
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
    key = record_visit(
        website_id=website_id,
        occurred_at=now,
        ip=ip,
        user_agent=user_agent,
        is_bot=is_bot,
        url_path=url_path,
    )
    if key:
        record_scope_presence(
            website_id=website_id,
            occurred_at=now,
            visitor_key=key,
            scopes=[("page", url_path), ("section", section_for_path(url_path))],
        )
    _maybe_rollup()


def ingest_custom_event(
    website_id: str,
    event_name: str,
    payload: dict[str, Any],
    device_info: dict[str, str | None],
    country: str | None,
    is_bot: bool = False,
    bot_reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert an anonymous custom event count.

    Only the event name is stored. Arbitrary event properties are rejected by
    omission in the view layer and never persisted. Custom events do not open or
    affect visits, but they do contribute to per-event **unique visitor** counts
    via the window digest derived from ``ip``/``user_agent`` (never persisted).
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
    if not is_bot:
        key = visitor_key_for(
            website_id=website_id, occurred_at=now, ip=ip, user_agent=user_agent
        )
        record_scope_presence(
            website_id=website_id,
            occurred_at=now,
            visitor_key=key,
            scopes=[("event", clean_name)],
        )
