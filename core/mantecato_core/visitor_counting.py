"""Exact, cookieless visitor/visit/bounce counting via compute-and-discard.

This module produces **exact** (not estimated) same-day metrics — unique
visitors, visits, bounce rate, pages-per-visit and on-site duration — without
cookies, browser storage, or any persistent per-person identifier.

How it stays compliant:

- At ingestion the server hashes ``(website_id + client IP + User-Agent)`` with
  a **random per-UTC-day salt** into an ephemeral digest (``visitor_key``). The
  IP and User-Agent are used transiently and never stored.
- The digest deduplicates a visitor *within a single day only*. The salt is
  regenerated each day and **deleted** by the nightly rollup, so digests can
  never be recomputed or linked across days (forward secrecy, no cross-day
  identity, no returning-visitor tracking).
- Only aggregate integer counts survive in :class:`VisitorDaily`.

Because there is no terminal storage/access, this falls outside ePrivacy
Art.5(3)/PECR; the transient processing of IP+UA rests on legitimate interest
(audience measurement). See ``docs/privacy.md``.

The previous HyperLogLog *estimator* (``visitor_estimation.py``) is replaced by
this exact counter.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet

# A visit ends after this much inactivity; the next hit starts a new visit.
SESSION_TIMEOUT_S = 30 * 60

# Fixed key for the transaction-scoped advisory lock that serialises rollups
# (so the lazy dashboard trigger and a scheduled run never double-count).
_ROLLUP_LOCK_KEY = 873_421_001

# Process-local cache of the current day's salt, refreshed at the UTC day
# boundary. Avoids a DB read per request. Keyed by UTC date.
_SALT_CACHE: dict[date, bytes] = {}
_SALT_LOCK = threading.Lock()


def utc_day(value: datetime) -> date:
    """Return the UTC calendar date of a (possibly naive) datetime."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()


def get_or_create_daily_salt(day: date) -> bytes:
    """Return the random salt for *day*, creating it lazily on first use.

    The salt is shared across all worker processes via a single
    ``visitor_day_salt`` row (created with ``INSERT ... ON CONFLICT DO NOTHING``
    semantics through ``get_or_create``) and cached in-process for the day.
    """
    cached = _SALT_CACHE.get(day)
    if cached is not None:
        return cached

    from apps.core.models import VisitorDaySalt

    row, _ = VisitorDaySalt.objects.get_or_create(
        day=day,
        defaults={"salt": secrets.token_bytes(32)},
    )
    salt = bytes(row.salt)
    with _SALT_LOCK:
        # Keep only the current day to bound memory; old salts are never
        # needed (events are stamped with "now").
        _SALT_CACHE.clear()
        _SALT_CACHE[day] = salt
    return salt


def compute_visitor_key(
    salt: bytes,
    *,
    website_id: str,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Derive the day-scoped, site-scoped dedup digest (hex).

    Uses the full IP and User-Agent to maximise dedup accuracy. The inputs are
    never stored; only this digest is, and only until the daily rollup discards
    the salt that produced it.
    """
    subject = "|".join([str(website_id), ip or "", user_agent or ""])
    return hmac.new(salt, subject.encode("utf-8"), hashlib.sha256).hexdigest()


def record_visit(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    user_agent: str | None,
    is_bot: bool,
) -> None:
    """Fold one **pageview** into the exact same-day visit/bounce state.

    Bots are ignored. Custom events do not drive visits and must not call this.
    """
    if is_bot:
        return

    from apps.core.models import VisitorDayState

    day = utc_day(occurred_at)
    salt = get_or_create_daily_salt(day)
    key = compute_visitor_key(salt, website_id=website_id, ip=ip, user_agent=user_agent)

    with transaction.atomic():
        row, created = VisitorDayState.objects.select_for_update().get_or_create(
            website_id=website_id,
            day=day,
            visitor_key=key,
            defaults={
                "first_seen": occurred_at,
                "last_seen": occurred_at,
                "visits": 1,
                "bounces": 0,
                "cur_visit_pageviews": 1,
                "cur_visit_duration_s": 0,
                "total_pageviews": 1,
                "total_duration_s": 0,
            },
        )
        if created:
            return

        gap = (occurred_at - row.last_seen).total_seconds()
        gap = max(0, int(gap))  # clamp clock skew / out-of-order events
        if gap > SESSION_TIMEOUT_S:
            # Close the previous visit, then open a new one.
            if row.cur_visit_pageviews <= 1:
                row.bounces += 1
            row.total_duration_s += row.cur_visit_duration_s
            row.visits += 1
            row.cur_visit_pageviews = 1
            row.cur_visit_duration_s = 0
        else:
            row.cur_visit_pageviews += 1
            row.cur_visit_duration_s += gap
        row.total_pageviews += 1
        row.last_seen = occurred_at
        row.save(
            update_fields=[
                "visits",
                "bounces",
                "cur_visit_pageviews",
                "cur_visit_duration_s",
                "total_pageviews",
                "total_duration_s",
                "last_seen",
            ]
        )


def aggregate_state(qs: QuerySet) -> dict[str, int]:
    """Aggregate a ``VisitorDayState`` queryset into exact totals.

    Closes the in-progress visit of each row on the fly: an open visit with a
    single pageview counts as a bounce, and its accumulated duration is added.
    Used both for the live (not-yet-rolled-up) days and as the rollup formula.
    """
    agg = qs.aggregate(
        unique_visitors=Count("id"),
        visits=Sum("visits"),
        closed_bounces=Sum("bounces"),
        open_bounces=Count("id", filter=Q(cur_visit_pageviews__lte=1)),
        total_pageviews=Sum("total_pageviews"),
        closed_duration=Sum("total_duration_s"),
        open_duration=Sum("cur_visit_duration_s"),
    )
    return {
        "unique_visitors": agg["unique_visitors"] or 0,
        "visits": agg["visits"] or 0,
        "bounces": (agg["closed_bounces"] or 0) + (agg["open_bounces"] or 0),
        "total_pageviews": agg["total_pageviews"] or 0,
        "total_duration_s": (agg["closed_duration"] or 0) + (agg["open_duration"] or 0),
    }


# ---------------------------------------------------------------------------
# Nightly rollup — finalise and discard past days (scheduler-free).
# ---------------------------------------------------------------------------


def has_unrolled_past_days(today: date | None = None) -> bool:
    """Cheap check: are there ephemeral rows for any day before *today*?"""
    from apps.core.models import VisitorDayState

    today = today or utc_day(timezone.now())
    return VisitorDayState.objects.filter(day__lt=today).exists()


def rollup_finished_days(today: date | None = None) -> dict[str, int]:
    """Aggregate every day before *today* into :class:`VisitorDaily`, then discard.

    For each ``(website_id, day)`` still in ``VisitorDayState`` with
    ``day < today`` the exact counts are folded into the permanent daily
    aggregate, the in-progress visit of each row is closed (single-pageview =
    bounce), and the ephemeral state + that day's salt are deleted.

    A Postgres transaction-scoped advisory lock serialises concurrent calls
    (the lazy dashboard trigger may fire from several workers at once), so the
    incremental add is never double-counted. Idempotent: a second run finds no
    state rows and does nothing.

    Returns ``{"days": ..., "rows": ..., "salts": ...}``.
    """
    from apps.core.models import VisitorDaily, VisitorDaySalt, VisitorDayState

    today = today or utc_day(timezone.now())
    result = {"days": 0, "rows": 0, "salts": 0}

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])

        groups = list(
            VisitorDayState.objects.filter(day__lt=today)
            .values("website_id", "day")
            .annotate(
                unique_visitors=Count("id"),
                visits=Sum("visits"),
                closed_bounces=Sum("bounces"),
                open_bounces=Count("id", filter=Q(cur_visit_pageviews__lte=1)),
                total_pageviews=Sum("total_pageviews"),
                closed_duration=Sum("total_duration_s"),
                open_duration=Sum("cur_visit_duration_s"),
            )
        )

        for g in groups:
            bounces = (g["closed_bounces"] or 0) + (g["open_bounces"] or 0)
            duration = (g["closed_duration"] or 0) + (g["open_duration"] or 0)
            obj, created = VisitorDaily.objects.get_or_create(
                website_id=g["website_id"],
                day=g["day"],
                scope="site",
                scope_value="",
                defaults={
                    "unique_visitors": g["unique_visitors"] or 0,
                    "visits": g["visits"] or 0,
                    "bounces": bounces,
                    "total_pageviews": g["total_pageviews"] or 0,
                    "total_duration_s": duration,
                },
            )
            if not created:
                # Late rows for an already-finalised day: add incrementally.
                VisitorDaily.objects.filter(pk=obj.pk).update(
                    unique_visitors=F("unique_visitors") + (g["unique_visitors"] or 0),
                    visits=F("visits") + (g["visits"] or 0),
                    bounces=F("bounces") + bounces,
                    total_pageviews=F("total_pageviews") + (g["total_pageviews"] or 0),
                    total_duration_s=F("total_duration_s") + duration,
                )
            result["days"] += 1

        deleted_rows, _ = VisitorDayState.objects.filter(day__lt=today).delete()
        deleted_salts, _ = VisitorDaySalt.objects.filter(day__lt=today).delete()
        result["rows"] = deleted_rows
        result["salts"] = deleted_salts

    return result


# ---------------------------------------------------------------------------
# Small shared helpers (moved here from the removed visitor_estimation module).
# ---------------------------------------------------------------------------


def section_for_path(path: str, depth: int = 2) -> str:
    """Return the URL-prefix section (first *depth* path segments)."""
    clean = (path or "/").split("?", 1)[0].split("#", 1)[0].strip("/")
    if not clean:
        return "/"
    parts = clean.split("/")[:depth]
    return "/" + "/".join(parts)


def has_only_bot_filter(filters: list[Any] | None) -> bool:
    """True when no content/device/geo narrowing is active.

    Visitor/visit counts come from aggregate tables that cannot be sliced by
    url/browser/country, so they are only shown when the active filters do not
    narrow the population (otherwise they are suppressed as ``None``).
    """
    return all(getattr(f, "column", "") == "__bot_filter__" for f in (filters or []))
