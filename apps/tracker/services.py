"""Tracker ingestion services — anonymous aggregate pageview recording.

This module is the write-path core of the analytics pipeline. It receives
validated payloads from :mod:`apps.tracker.views` and inserts rows into the
``website_event`` table using raw SQL via :func:`core.mantecato_core.database.raw_query`.

Privacy-first design (per PLAN.md):
- No session_id or visit_id — every pageview is independent and anonymous.
- Only the referrer **domain** is kept (for aggregate traffic sources); the full
  referrer URL, its query string, UTM params and click IDs are never stored.
- Custom events store only the event name; no payload/properties.
- No identify calls, revenue tracking, or session data.
- Only the minimal data needed for aggregate pageview analytics is stored:
  url_path, url_query, page_title, event_name, hostname, referrer_domain, and
  device/browser/geo metadata for aggregate breakdowns and bot detection.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from django.utils import timezone

from core.mantecato_core.database import raw_query
from core.mantecato_core.visitor_counting import (
    record_engagement,
    record_scope_presence,
    record_visit,
    section_for_path,
    visitor_key_for,
)

logger = logging.getLogger(__name__)

# Upper bound on a single engagement beacon's reported active seconds, to cap
# abuse from a tampered client. A genuine long read still accrues up to this.
_MAX_ENGAGEMENT_S = 3600

# Throttle for the lazy, scheduler-free rollup piggybacked on ingestion.
_ROLLUP_MIN_INTERVAL_S = 3600
_last_rollup_attempt = None

# Short-lived process-local cache of active website UUIDs so the unauthenticated
# ingest endpoint can cheaply reject events for unknown sites — blocking metric
# poisoning of arbitrary UUIDs and unbounded storage growth for non-existent
# websites (website_id is a bare UUIDField with no FK).
_WEBSITE_CACHE_TTL_S = 60
_website_cache: frozenset[str] = frozenset()
_website_cache_at: float = 0.0
_website_cache_lock = threading.Lock()


def is_trackable_website(website_id: str) -> bool:
    """Return ``True`` when *website_id* is a known, active (non-deleted) site.

    Backed by a TTL cache so the check costs at most one query per refresh
    interval on the hot path; a newly created site becomes trackable within
    ``_WEBSITE_CACHE_TTL_S`` seconds. Malformed (non-UUID) ids return ``False``,
    which also keeps junk out of the bare ``website_event.website_id`` column.
    """
    if not website_id:
        return False
    try:
        normalized = str(uuid.UUID(str(website_id)))
    except (ValueError, AttributeError, TypeError):
        return False

    global _website_cache, _website_cache_at  # noqa: PLW0603  process-local cache
    now = time.monotonic()
    if now - _website_cache_at >= _WEBSITE_CACHE_TTL_S:
        with _website_cache_lock:
            if now - _website_cache_at >= _WEBSITE_CACHE_TTL_S:
                from apps.core.models import Website

                _website_cache = frozenset(
                    str(wid)
                    for wid in Website.objects.filter(is_deleted=False).values_list("id", flat=True)
                )
                _website_cache_at = now
    return normalized in _website_cache


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
            _finished_period_keys,
            discard_expired_digests,
            rollup_finished_periods,
        )

        # Expire over-retention digests every throttle tick, not only when a month
        # finalises — otherwise a fixed monthly window would null them just once a
        # month. Cheap when caught up (matches no rows); independent of the rollup.
        discard_expired_digests(now)
        # Compute the finished-window set once and reuse it as both the guard and the
        # rollup input, so the period keys are scanned a single time per tick.
        finished = _finished_period_keys(now)
        if finished:
            rollup_finished_periods(now, finished_keys=finished)
    except Exception:
        logger.warning("Lazy visitor rollup failed; will retry later", exc_info=True)


def _parse_url(url: str) -> dict[str, str | None]:
    """Parse a page URL into its path component.

    The query string is intentionally **discarded and never stored**: it can carry
    personal data (``?email=``, ``?token=``...) with no place in privacy-first
    aggregate analytics, so ``url_query`` is always ``None``. The URL fragment is
    likewise dropped — **except** a hash-based SPA route (``#/dashboard``), which is
    kept so per-route counts survive. A fragment that smells like a credential
    carrier (contains ``=`` or ``&``, e.g. ``#access_token=...``) is never kept.

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
    path = unquote(path)
    # Hash-based SPA routes (``#/dashboard``) carry the page identity in the
    # fragment, so keep them. But a fragment can also smuggle credentials
    # (``#access_token=...``), so only restore one that looks like a route: starts
    # with "/" and has no query-like ``=``/``&``. Decode first so a ``%3D``-encoded
    # token can't slip past the filter.
    frag = unquote(parsed.fragment)
    if frag.startswith("/") and "=" not in frag and "&" not in frag:
        path = f"{path}#{frag}"
    return {"url_path": path[:500], "url_query": None}


def _referrer_domain(referrer: str | None, hostname: str | None) -> str | None:
    """Reduce a raw referrer URL to its bare domain for aggregate source counts.

    Only the registrable host is kept (``www.`` stripped); the referrer's path and
    query string are parsed transiently and **never stored** (they can carry PII).
    Same-site referrals (host equal to the page's own hostname) and missing/empty
    referrers collapse to ``None`` — counted as direct traffic. No UTM/click IDs.
    """
    if not referrer:
        return None
    try:
        host = (urlparse(referrer).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return None
    if not host:
        return None
    own = (hostname or "").lower().removeprefix("www.")
    if own and host == own:
        return None
    return host[:255]


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

    # Compute the window digest up front (best-effort). It is stored on the durable
    # event row below even if the visit-state fold fails; a ``None`` only degrades
    # unique-visitor counting for this one row — the pageview itself is still kept.
    # The digest is computed for bots too so the bot filter stays a dynamic toggle.
    try:
        event_key: str | None = visitor_key_for(
            website_id=website_id, occurred_at=now, ip=ip, user_agent=user_agent
        )
    except Exception:
        event_key = None
        logger.warning(
            "visitor_key computation failed; storing pageview without digest",
            exc_info=True,
        )

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, created_at,
             url_path, url_query,
             page_title, event_type, event_name, hostname,
             browser, os, device,
             country, is_bot, bot_reason, visitor_key, referrer_domain)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}},
             {{pageTitle}}, 1, NULL, {{hostname}},
             {{browser}}, {{os}}, {{device}},
             {{country}}, {{isBot}}, {{botReason}}, {{visitorKey}}, {{referrerDomain}})
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
            "visitorKey": event_key,
            "referrerDomain": _referrer_domain(payload.get("referrer"), payload.get("hostname")),
        },
    )
    # Best-effort visit/bounce fold AFTER the durable write, so a row-lock or
    # contention error in ``record_visit`` can never lose the pageview. Bots open
    # no visit (``record_visit`` returns ``None``); humans also get scope presence.
    try:
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
    except Exception:
        logger.warning("visit-state fold failed; pageview already stored", exc_info=True)
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

    # Digest computed for everyone (incl. bots) so bot custom events are counted
    # separately for the dynamic bot-filter toggle; scope presence stays human-only.
    # Best-effort: a digest failure must not drop the durable custom-event row below.
    try:
        event_key: str | None = visitor_key_for(
            website_id=website_id, occurred_at=now, ip=ip, user_agent=user_agent
        )
    except Exception:
        event_key = None
        logger.warning(
            "visitor_key computation failed; storing custom event without digest",
            exc_info=True,
        )

    raw_query(
        """
        INSERT INTO website_event
            (event_id, website_id, created_at,
             url_path, url_query,
             page_title, event_type, event_name, hostname,
             browser, os, device,
             country, is_bot, bot_reason, visitor_key)
        VALUES
            ({{eventId::uuid}}, {{websiteId::uuid}}, {{createdAt::timestamptz}},
             {{urlPath}}, {{urlQuery}},
             {{pageTitle}}, 2, {{eventName}}, {{hostname}},
             {{browser}}, {{os}}, {{device}},
             {{country}}, {{isBot}}, {{botReason}}, {{visitorKey}})
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
            "visitorKey": event_key,
        },
    )
    if not is_bot and event_key:
        try:
            record_scope_presence(
                website_id=website_id,
                occurred_at=now,
                visitor_key=event_key,
                scopes=[("event", clean_name)],
            )
        except Exception:
            logger.warning(
                "event scope-presence failed; custom event already stored", exc_info=True
            )


def ingest_engagement(
    website_id: str,
    payload: dict[str, Any],
    is_bot: bool = False,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Fold an engagement heartbeat into the visitor's open visit.

    The beacon carries the cumulative active (tab-visible) seconds spent on the
    current page. It updates the ephemeral visit state for accurate on-site
    duration and the engaged-bounce decision, and writes **no** ``website_event``
    row (engagement is not a pageview). The ``ip``/``user_agent`` are used
    transiently to re-derive the same window digest and are never persisted.
    """
    if is_bot:
        return
    try:
        seconds = int(float(payload.get("seconds", 0)))
    except (TypeError, ValueError):
        return
    if seconds <= 0:
        return

    record_engagement(
        website_id=website_id,
        occurred_at=timezone.now(),
        ip=ip,
        user_agent=user_agent,
        seconds=min(seconds, _MAX_ENGAGEMENT_S),
        is_bot=is_bot,
    )
