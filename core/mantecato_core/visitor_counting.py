"""Exact, cookieless visitor/visit/bounce counting via compute-and-discard.

Produces **exact** (not estimated) metrics — unique visitors, visits, bounce
rate, pages-per-visit, on-site duration — without cookies, browser storage, or
any persistent per-person identifier.

How it stays compliant:

- At ingestion the server hashes ``(website_id + truncated client IP + User-Agent)``
  with a **random per-window salt** into an ephemeral digest (``visitor_key``).
  The IP is always coarsened (``/24`` IPv4, ``/48`` IPv6) before hashing, and the
  IP/User-Agent are used transiently and never stored.
- The digest deduplicates a visitor **within one fixed calendar month**. The salt
  is regenerated each month and **deleted** by the rollup, so digests can never be
  recomputed or linked across months (forward secrecy; no cross-window identity,
  no returning-visitor tracking).
- Only aggregate integer counts survive (:class:`VisitorDaily` per day,
  :class:`VisitorPeriod` per window).

The dedup window, the IP truncation and the retention are **fixed and not
configurable** so the privacy posture cannot be misconfigured. Because there is no
terminal storage/access this falls outside ePrivacy Art.5(3)/PECR regardless; the
transient truncated-IP+UA processing rests on the consent-exempt audience-measurement
basis (first-party, IP masked, identifier ≤ 13 months). See ``docs/privacy.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, F, Min, Q, Sum
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

# A visit ends after this much inactivity; the next hit starts a new visit.
SESSION_TIMEOUT_S = 30 * 60

# Fixed key for the transaction-scoped advisory lock that serialises rollups.
_ROLLUP_LOCK_KEY = 873_421_001

# The dedup (salt) window is FIXED to one calendar month — not configurable. A
# fixed monthly salt is a calendar period (never sliding/per-visit) well under the
# 13-month CNIL/Garante identifier ceiling, so the cookieless digest stays inside
# the consent-exempt audience-measurement envelope by construction. See docs/privacy.md.
_WINDOW = "month"

# Network prefix kept from the client IP before it feeds the digest hash — FIXED,
# not configurable. /24 (IPv4) / /48 (IPv6) is the minimisation Garante (mask the
# 4th octet) / CNIL (drop the last octet) require for a consent-exempt audience
# identifier. Geo (country) and datacenter-bot detection still use the full IP.
_DIGEST_IPV4_PREFIX = 24
_DIGEST_IPV6_PREFIX = 48

# Process-local cache of the current window's salt. Keyed by period key.
_SALT_CACHE: dict[str, bytes] = {}
_SALT_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Exactness window helpers
# ---------------------------------------------------------------------------


def _window() -> str:
    """Return the dedup window — always ``month`` (fixed, not configurable).

    A returning visitor is deduplicated within the calendar month and counted once
    per month over any range; the salt rotates monthly. See ``docs/privacy.md``.
    """
    return _WINDOW


def current_window() -> str:
    """Public accessor for the dedup window (always ``month``)."""
    return _WINDOW


def utc_day(value: datetime) -> date:
    """Return the UTC calendar date of a (possibly naive) datetime."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()


def _period_key_for_date(d: date, window: str) -> str:
    """Return the period key for *d*: month ``2026-06`` (or day ``2026-06-08`` /
    week ``2026-W23`` for legacy rows)."""
    if window == "day":
        return d.isoformat()
    if window == "week":
        iso = d.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    return f"{d.year:04d}-{d.month:02d}"


def period_key(value: datetime, window: str | None = None) -> str:
    """Return the exactness-window key containing *value*."""
    return _period_key_for_date(utc_day(value), window or _window())


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _period_bounds(d: date, window: str) -> tuple[date, date]:
    """Return (first_day, last_day) of the window containing date *d*."""
    if window == "day":
        return d, d
    if window == "week":
        start = d - timedelta(days=d.weekday())  # ISO week starts Monday
        return start, start + timedelta(days=6)
    return d.replace(day=1), _month_end(d)


def periods_in_range(start_day: date, end_day: date, window: str) -> list[tuple[str, date, date]]:
    """List ``(period_key, period_start, period_end)`` for windows overlapping the range."""
    out: list[tuple[str, date, date]] = []
    cur_start, cur_end = _period_bounds(start_day, window)
    while cur_start <= end_day:
        out.append((_period_key_for_date(cur_start, window), cur_start, cur_end))
        cur_start, cur_end = _period_bounds(cur_end + timedelta(days=1), window)
    return out


def current_period_key() -> str:
    """Return the window key for 'now'."""
    return period_key(timezone.now())


def current_window_start() -> date:
    """First calendar day of the current (live) exactness window."""
    start, _ = _period_bounds(utc_day(timezone.now()), _window())
    return start


# ---------------------------------------------------------------------------
# Salt + digest
# ---------------------------------------------------------------------------


def get_or_create_salt(period: str) -> bytes:
    """Return the random salt for *period*, creating it lazily on first use.

    Shared across worker processes via a single ``visitor_salt`` row and cached
    in-process for the current window.
    """
    cached = _SALT_CACHE.get(period)
    if cached is not None:
        return cached

    from apps.core.models import VisitorSalt

    row, _ = VisitorSalt.objects.get_or_create(
        period=period,
        defaults={"salt": secrets.token_bytes(32)},
    )
    salt = bytes(row.salt)
    with _SALT_LOCK:
        # Bounded cache: read paths and the rollup can touch several windows in
        # one process (e.g. ranges spanning a month boundary), so keep a few
        # rather than clearing to one (which thrashed under multi-window access).
        if len(_SALT_CACHE) >= 8:
            _SALT_CACHE.clear()
        _SALT_CACHE[period] = salt
    return salt


def compute_visitor_key(
    salt: bytes,
    *,
    website_id: str,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Derive the month-scoped, site-scoped dedup digest (hex).

    The IP is always coarsened to ``/24`` (IPv4) / ``/48`` (IPv6) before hashing
    (:data:`_DIGEST_IPV4_PREFIX` / :data:`_DIGEST_IPV6_PREFIX`), so the monthly salt
    cannot turn the digest into a precise fingerprint — the CNIL/Garante IP-masking
    condition, applied unconditionally. The IP/User-Agent inputs are never stored;
    only this digest is, and only until the rollup discards the salt.
    """
    if ip:
        from apps.tracker.ip import truncate_ip

        ip = truncate_ip(ip, _DIGEST_IPV4_PREFIX, _DIGEST_IPV6_PREFIX)
    subject = "|".join([str(website_id), ip or "", user_agent or ""])
    return hmac.new(salt, subject.encode("utf-8"), hashlib.sha256).hexdigest()


def visitor_key_for(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Return the current-window digest for a request (for per-scope presence).

    Same digest :func:`record_visit` computes, without touching visit state —
    used for custom events (which don't open visits but still contribute to
    per-event unique-visitor counts).
    """
    period = _period_key_for_date(utc_day(occurred_at), _window())
    return compute_visitor_key(
        get_or_create_salt(period), website_id=website_id, ip=ip, user_agent=user_agent
    )


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


def _bounce_threshold() -> int:
    """On-page **active** seconds below which a single-pageview visit is a bounce.

    Powered by engagement beacons (:func:`record_engagement`). ``0`` ⇒ the
    classic rule (a single-pageview visit is always a bounce, regardless of
    time), matching Umami. Configured by ``settings.BOUNCE_ENGAGEMENT_THRESHOLD_S``.
    """
    return max(0, int(getattr(settings, "BOUNCE_ENGAGEMENT_THRESHOLD_S", 10)))


def _open_bounce_filter(threshold: int) -> Q:
    """Q matching in-progress visits that count as bounces.

    A single-pageview open visit (so ``cur_visit_duration_s == 0`` and its whole
    duration is the current page's engaged time) is a bounce when that engaged
    time is below *threshold*; with ``threshold <= 0`` every single-pageview visit
    bounces (classic rule).
    """
    q = Q(cur_visit_pageviews__lte=1)
    if threshold > 0:
        q &= Q(cur_page_engaged_s__lt=threshold)
    return q


def record_visit(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    user_agent: str | None,
    is_bot: bool,
    url_path: str | None = None,
) -> str | None:
    """Fold one **pageview** into the exact visit/bounce state.

    Bots are ignored (returns ``None``). Custom events do not drive visits.
    Returns the visitor digest (so the caller can record per-scope presence),
    or ``None`` for bots.
    """
    if is_bot:
        return None

    from apps.core.models import VisitorDayState

    day = utc_day(occurred_at)
    period = _period_key_for_date(day, _window())
    salt = get_or_create_salt(period)
    key = compute_visitor_key(salt, website_id=website_id, ip=ip, user_agent=user_agent)
    entry = (url_path or "/")[:500]

    with transaction.atomic():
        row, created = VisitorDayState.objects.select_for_update().get_or_create(
            website_id=website_id,
            day=day,
            visitor_key=key,
            defaults={
                "period": period,
                "entry_path": entry,
                "first_seen": occurred_at,
                "last_seen": occurred_at,
                "visits": 1,
                "bounces": 0,
                "cur_visit_pageviews": 1,
                "cur_visit_duration_s": 0,
                "cur_page_engaged_s": 0,
                "total_pageviews": 1,
                "total_duration_s": 0,
            },
        )
        if created:
            return key

        threshold = _bounce_threshold()
        gap = max(0, int((occurred_at - row.last_seen).total_seconds()))
        fields = [
            "visits",
            "bounces",
            "cur_visit_pageviews",
            "cur_visit_duration_s",
            "cur_page_engaged_s",
            "total_pageviews",
            "total_duration_s",
            "last_seen",
        ]
        if gap > SESSION_TIMEOUT_S:
            # Close the previous visit, then open a new one (new landing page).
            # Its duration = folded completed pages + the last page's engaged time.
            prev_dur = row.cur_visit_duration_s + row.cur_page_engaged_s
            if row.cur_visit_pageviews <= 1 and (threshold <= 0 or prev_dur < threshold):
                row.bounces += 1
            row.total_duration_s += prev_dur
            row.visits += 1
            row.cur_visit_pageviews = 1
            row.cur_visit_duration_s = 0
            row.cur_page_engaged_s = 0
            row.entry_path = entry
            fields.append("entry_path")
        else:
            # Same visit, new page: fold the page that just ended. Prefer its
            # measured active (engaged) time; fall back to the wall-clock gap when
            # no engagement beacon was received for it (older clients / imports).
            page_dur = row.cur_page_engaged_s if row.cur_page_engaged_s > 0 else gap
            row.cur_visit_duration_s += page_dur
            row.cur_page_engaged_s = 0
            row.cur_visit_pageviews += 1
        row.total_pageviews += 1
        row.last_seen = occurred_at
        row.save(update_fields=fields)
        return key


def record_engagement(
    *,
    website_id: str,
    occurred_at: datetime,
    ip: str | None,
    user_agent: str | None,
    seconds: int,
    is_bot: bool = False,
) -> None:
    """Fold a heartbeat's on-page **active** time into the visitor's open visit.

    Engagement beacons report the cumulative active (tab-visible) seconds spent on
    the current page. They update the open visit's duration and keep the session
    alive **without** opening a visit or writing an event row, so single-page
    visits accrue real on-page time (accurate duration + engaged bounce). Ignored
    for bots, for visitors with no recorded pageview, and for stale beacons that
    arrive after the visit's inactivity timeout (so a dead visit is never revived).
    """
    if is_bot:
        return
    seconds = max(0, int(seconds or 0))

    from apps.core.models import VisitorDayState

    day = utc_day(occurred_at)
    period = _period_key_for_date(day, _window())
    salt = get_or_create_salt(period)
    key = compute_visitor_key(salt, website_id=website_id, ip=ip, user_agent=user_agent)

    with transaction.atomic():
        row = (
            VisitorDayState.objects.select_for_update()
            .filter(website_id=website_id, day=day, visitor_key=key)
            .first()
        )
        if row is None:
            return  # engagement with no recorded pageview → ignore
        if (occurred_at - row.last_seen).total_seconds() > SESSION_TIMEOUT_S:
            return  # beacon after the visit closed → don't revive a dead visit
        fields: list[str] = []
        if seconds > row.cur_page_engaged_s:
            row.cur_page_engaged_s = seconds
            fields.append("cur_page_engaged_s")
        if occurred_at > row.last_seen:
            row.last_seen = occurred_at
            fields.append("last_seen")
        if fields:
            row.save(update_fields=fields)


def record_scope_presence(
    *,
    website_id: str,
    occurred_at: datetime,
    visitor_key: str,
    scopes: list[tuple[str, str]],
) -> None:
    """Record that *visitor_key* was seen on each ``(scope, scope_value)`` this window.

    Enables exact per-page/section/event unique-visitor counts. Idempotent per
    window via the unique constraint. Skipped for bots (no ``visitor_key``).
    """
    if not visitor_key or not scopes:
        return

    from apps.core.models import VisitorScopeState

    period = _period_key_for_date(utc_day(occurred_at), _window())
    for scope, scope_value in scopes:
        VisitorScopeState.objects.get_or_create(
            website_id=website_id,
            period=period,
            scope=scope,
            scope_value=(scope_value or "")[:500],
            visitor_key=visitor_key,
        )


def aggregate_state(qs: QuerySet) -> dict[str, int]:
    """Aggregate a ``VisitorDayState`` queryset into exact totals.

    ``unique_visitors`` counts **distinct** visitor digests (so a visitor active
    on several days of the window counts once). The in-progress visit of each row
    is closed on the fly: a single-pageview open visit is a bounce when its active
    on-page time is below the engaged threshold, and both its folded and current-
    page durations are added. Used for the live window and as the rollup formula.
    """
    threshold = _bounce_threshold()
    agg = qs.aggregate(
        unique_visitors=Count("visitor_key", distinct=True),
        visits=Sum("visits"),
        closed_bounces=Sum("bounces"),
        open_bounces=Count("id", filter=_open_bounce_filter(threshold)),
        total_pageviews=Sum("total_pageviews"),
        closed_duration=Sum("total_duration_s"),
        open_duration=Sum("cur_visit_duration_s"),
        open_engaged=Sum("cur_page_engaged_s"),
    )
    return {
        "unique_visitors": agg["unique_visitors"] or 0,
        "visits": agg["visits"] or 0,
        "bounces": (agg["closed_bounces"] or 0) + (agg["open_bounces"] or 0),
        "total_pageviews": agg["total_pageviews"] or 0,
        "total_duration_s": (agg["closed_duration"] or 0)
        + (agg["open_duration"] or 0)
        + (agg["open_engaged"] or 0),
    }


# ---------------------------------------------------------------------------
# Rollup — finalise and discard past windows (scheduler-free).
# ---------------------------------------------------------------------------


def _finished_period_keys(now: datetime | None = None) -> set[str]:
    """Period keys (across day- and scope-state) whose window has fully ended.

    A window is *finished* once its last calendar day falls before the first day of
    the current month. Deriving this from each key's real calendar bounds — rather
    than string-comparing against the current month key — keeps the rollup correct
    when legacy rows carry a finer-grained key (``2026-06-08`` / ``2026-W23``) from a
    deployment that predates the fixed monthly window: such a key *inside* the current
    month must stay live, not be mistaken for a past period and finalised mid-month
    (which would prematurely delete the open month's state and corrupt its totals).
    """
    from apps.core.models import VisitorDayState, VisitorScopeState

    month_start, _ = _period_bounds(utc_day(now or timezone.now()), _window())
    keys = set(VisitorDayState.objects.values_list("period", flat=True).distinct())
    keys |= set(VisitorScopeState.objects.values_list("period", flat=True).distinct())
    return {k for k in keys if _period_ended(k, month_start)}


def discard_expired_digests(now: datetime | None = None) -> int:
    """NULL the per-event ``visitor_key`` digests older than the retention window.

    Split out of :func:`rollup_finished_periods` so the lazy write-path can run it on
    its own throttled cadence — otherwise, with a fixed monthly window, the only
    digest-expiry pass would fire once a month (when a finished month exists to roll
    up) instead of keeping pace as events cross the retention cutoff. Returns the
    number of rows nulled. Idempotent: once caught up it matches nothing.
    """
    from apps.core.models import WebsiteEvent

    retention = int(getattr(settings, "VISITOR_KEY_RETENTION_DAYS", 396))
    cutoff = (now or timezone.now()) - timedelta(days=retention)
    return WebsiteEvent.objects.filter(created_at__lt=cutoff, visitor_key__isnull=False).update(
        visitor_key=None
    )


def rollup_finished_periods(
    now: datetime | None = None, finished_keys: set[str] | None = None
) -> dict[str, int]:
    """Finalise every window before the current one, then discard its digests.

    Writes per-day site aggregates (:class:`VisitorDaily`, for the daily trend),
    per-window aggregates (:class:`VisitorPeriod`, with **exact** window-unique
    visitors and per-scope/landing breakdowns), then deletes the window's
    ephemeral state, scope-presence rows and salt. A Postgres advisory lock
    serialises concurrent calls; idempotent (a second run finds no state).

    *finished_keys* lets a caller that has already computed the finished set (e.g.
    the write-path guard) pass it in, avoiding a second scan of the period keys.

    Returns ``{"periods", "rows", "salts", "scope_rows"}``.
    """
    from apps.core.models import (
        VisitorDaily,
        VisitorDayState,
        VisitorPeriod,
        VisitorSalt,
        VisitorScopeState,
    )

    window = _window()
    threshold = _bounce_threshold()
    month_start, _ = _period_bounds(utc_day(now or timezone.now()), window)
    if finished_keys is None:
        finished_keys = _finished_period_keys(now)
    result = {"periods": 0, "rows": 0, "salts": 0, "scope_rows": 0}

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])

        # Finalise only windows that have *ended* (by calendar bounds, robust to
        # legacy day/week keys); current-month rows — whatever their key — stay live.
        finished = VisitorDayState.objects.filter(period__in=finished_keys)

        # Aggregates store **all** visitors (humans + bots). The bot filter — and
        # every other filter — is applied **downstream at read time**, never baked
        # into the stored data, so the DB is identical whatever the filter.

        # 1) Per-day site aggregates (daily trend).
        for g in finished.values("website_id", "day").annotate(
            unique_visitors=Count("visitor_key", distinct=True),
            visits=Sum("visits"),
            closed_bounces=Sum("bounces"),
            open_bounces=Count("id", filter=_open_bounce_filter(threshold)),
            total_pageviews=Sum("total_pageviews"),
            closed_duration=Sum("total_duration_s"),
            open_duration=Sum("cur_visit_duration_s"),
            open_engaged=Sum("cur_page_engaged_s"),
        ):
            _upsert_daily(VisitorDaily, g, website_id=g["website_id"], day=g["day"])

        # 2) Per-window site aggregates (exact window uniques).
        for g in finished.values("website_id", "period").annotate(
            unique_visitors=Count("visitor_key", distinct=True),
            visits=Sum("visits"),
            closed_bounces=Sum("bounces"),
            open_bounces=Count("id", filter=_open_bounce_filter(threshold)),
            total_pageviews=Sum("total_pageviews"),
            closed_duration=Sum("total_duration_s"),
            open_duration=Sum("cur_visit_duration_s"),
            open_engaged=Sum("cur_page_engaged_s"),
            min_day=Min("day"),
        ):
            p_start, _ = _period_bounds(g["min_day"], window)
            _upsert_period(VisitorPeriod, g, website_id=g["website_id"], period_start=p_start)
            result["periods"] += 1

        # 3) Per-window landing-page bounce (entry page of each visitor's last visit).
        for g in (
            finished.values("website_id", "period", "entry_path")
            .annotate(
                visits=Count("id"),
                bounces=Count("id", filter=_open_bounce_filter(threshold)),
                min_day=Min("day"),
            )
            .exclude(entry_path__isnull=True)
        ):
            p_start, _ = _period_bounds(g["min_day"], window)
            _upsert_period_counts(
                VisitorPeriod,
                website_id=g["website_id"],
                period_start=p_start,
                scope="landing",
                scope_value=g["entry_path"] or "/",
                visits=g["visits"] or 0,
                bounces=g["bounces"] or 0,
            )

        # 4) Per-window per-scope unique visitors (pages/sections/events).
        scope_qs = VisitorScopeState.objects.filter(period__in=finished_keys)
        for g in scope_qs.values("website_id", "period", "scope", "scope_value").annotate(
            unique_visitors=Count("visitor_key", distinct=True),
        ):
            p_start, _ = _period_bounds(_first_day_of_period(g["period"], window), window)
            _upsert_period_counts(
                VisitorPeriod,
                website_id=g["website_id"],
                period_start=p_start,
                scope=g["scope"],
                scope_value=g["scope_value"],
                unique_visitors=g["unique_visitors"] or 0,
            )

        # 5) NULL the per-event digests beyond the retention window (kept until then
        #    so visitor metrics stay exact and filterable), then discard the finalised
        #    windows' ephemeral state and their salts. Only salts whose own window has
        #    ended are dropped, so a still-open legacy day-key's salt is preserved.
        discard_expired_digests(now)
        result["scope_rows"], _ = scope_qs.delete()
        result["rows"], _ = finished.delete()
        expired_salts = [
            p
            for p in VisitorSalt.objects.values_list("period", flat=True)
            if _period_ended(p, month_start)
        ]
        result["salts"], _ = VisitorSalt.objects.filter(period__in=expired_salts).delete()

    return result


def aggregate_events_into_daily(website_id: str | None = None) -> dict[str, int]:
    """Sessionise imported per-event digests into the permanent aggregates, then discard them.

    Handles data that has ``website_event.visitor_key`` but **no**
    ``VisitorDayState`` — i.e. **imported** Umami pageviews (whose ``session_id``
    the importer hashes into ``visitor_key``). The live path is handled by the
    ``VisitorDayState`` rollup; ``(site, day)`` pairs that already have live state
    are skipped to avoid double counting.

    For each imported ``(site, day)`` it sessionises events per digest (30-min
    gap) into exact site-level visitors/visits/bounces/duration, plus per-page and
    per-section unique visitors (``VisitorPeriod`` scopes ``page``/``section``),
    upserts ``VisitorDaily``/``VisitorPeriod``, then NULLs the processed digests.

    Double-count safety: a ``(site, day)`` is skipped when it has live
    ``VisitorDayState`` **or** already has a ``VisitorDaily`` site row. The rollup
    deletes ``VisitorDayState`` once a window finalises but keeps ``visitor_key``
    until retention (for read-time exactness), so the ``VisitorDaily`` check is
    what stops already-rolled-up live days from being re-aggregated here. As a
    consequence, importing historical data into a day that already has live
    aggregates is a no-op for that day. The whole pass runs under the rollup's
    advisory lock so it cannot interleave with a concurrent rollup. Idempotent
    (nulled rows are skipped on re-run). Pure-Python → works on PostgreSQL and
    SQLite. Returns ``{"days", "events"}``.
    """
    from collections import defaultdict
    from itertools import groupby

    from apps.core.models import VisitorDaily, VisitorDayState, VisitorPeriod, WebsiteEvent

    window = _window()
    qs = WebsiteEvent.objects.filter(event_type=1, is_bot=False, visitor_key__isnull=False)
    if website_id is not None:
        qs = qs.filter(website_id=website_id)

    site_acc: dict[tuple[str, date], dict[str, int]] = {}
    keys_by_site: dict[str, list[str]] = defaultdict(list)
    # Per-(period, scope, scope_value) sets of distinct visitor digests, so the
    # anonymous aggregate also carries exact per-page / per-section unique visitors.
    scope_presence: dict[tuple[str, date, str, str], set[str]] = defaultdict(set)
    nulled = 0

    with transaction.atomic():
        # Serialise against the opportunistic/scheduled rollup (same advisory lock
        # key): both read website_event.visitor_key + VisitorDayState and do
        # additive upserts into the same VisitorDaily/VisitorPeriod rows, so they
        # must not interleave. Held across the read scan + writes below.
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])

        # (site, day) pairs already accounted for: currently-live state
        # (VisitorDayState) OR days already folded into VisitorDaily by the rollup
        # or a previous backfill. Skipping the latter is what prevents
        # re-aggregating (double-counting) already-rolled-up live days, since the
        # rollup keeps visitor_key on those events until retention.
        ds_qs = VisitorDayState.objects.all()
        vd_qs = VisitorDaily.objects.filter(scope="site")
        if website_id is not None:
            ds_qs = ds_qs.filter(website_id=website_id)
            vd_qs = vd_qs.filter(website_id=website_id)
        accounted_days = {
            (str(w), d) for (w, d) in ds_qs.values_list("website_id", "day").distinct()
        }
        accounted_days |= {
            (str(w), d) for (w, d) in vd_qs.values_list("website_id", "day").distinct()
        }

        rows = (
            qs.order_by("website_id", "visitor_key", "created_at")
            .values("website_id", "visitor_key", "created_at", "url_path")
            .iterator()
        )
        for (site, key), grp in groupby(
            rows, key=lambda r: (str(r["website_id"]), r["visitor_key"])
        ):
            events = list(grp)
            times = [r["created_at"] for r in events]
            day = utc_day(times[0])
            if (site, day) in accounted_days:
                continue
            keys_by_site[site].append(key)

            # Sessionise (30-min inactivity gap). visit_pv = pageviews in current visit.
            visits = 1
            visit_pv = 1
            total_dur = 0
            cur_dur = 0
            last = times[0]
            visit_pvs: list[int] = []
            for t in times[1:]:
                gap = max(0, int((t - last).total_seconds()))
                if gap > SESSION_TIMEOUT_S:
                    visit_pvs.append(visit_pv)
                    total_dur += cur_dur
                    visits += 1
                    visit_pv = 1
                    cur_dur = 0
                else:
                    visit_pv += 1
                    cur_dur += gap
                last = t
            visit_pvs.append(visit_pv)
            total_dur += cur_dur
            bounces = sum(1 for pv in visit_pvs if pv <= 1)

            acc = site_acc.setdefault(
                (site, day),
                {
                    "unique_visitors": 0,
                    "visits": 0,
                    "bounces": 0,
                    "total_pageviews": 0,
                    "total_duration_s": 0,
                },
            )
            acc["unique_visitors"] += 1
            acc["visits"] += visits
            acc["bounces"] += bounces
            acc["total_pageviews"] += len(times)
            acc["total_duration_s"] += total_dur

            p_start, _ = _period_bounds(day, window)
            pages = {(r["url_path"] or "/")[:500] for r in events}
            for page in pages:
                scope_presence[(site, p_start, "page", page)].add(key)
            for sec in {section_for_path(p) for p in pages}:
                scope_presence[(site, p_start, "section", sec)].add(key)

        if not site_acc:
            return {"days": 0, "events": 0}

        for (site, day), acc in site_acc.items():
            p_start, _ = _period_bounds(day, window)
            _upsert_counts(
                VisitorDaily,
                {"website_id": site, "day": day, "scope": "site", "scope_value": ""},
                acc,
            )
            _upsert_counts(
                VisitorPeriod,
                {"website_id": site, "period_start": p_start, "scope": "site", "scope_value": ""},
                acc,
            )
        for (s_site, sp_start, scope, scope_value), keyset in scope_presence.items():
            _upsert_period_counts(
                VisitorPeriod,
                website_id=s_site,
                period_start=sp_start,
                scope=scope,
                scope_value=scope_value,
                unique_visitors=len(keyset),
            )
        for site, keys in keys_by_site.items():
            for i in range(0, len(keys), 1000):
                nulled += WebsiteEvent.objects.filter(
                    website_id=site, visitor_key__in=keys[i : i + 1000]
                ).update(visitor_key=None)

    return {"days": len(site_acc), "events": nulled}


def _first_day_of_period(period: str, window: str | None = None) -> date:
    """Parse a period key back to its first calendar day.

    The format is auto-detected from the key itself (``window`` is accepted for
    backwards compatibility but ignored), so the rollup stays correct even when the
    operator has just changed ``VISITOR_EXACT_WINDOW`` and older rows still carry a
    period key in the previous format.
    """
    if "-W" in period:
        year_s, week_s = period.split("-W")
        return date.fromisocalendar(int(year_s), int(week_s), 1)
    if "-Q" in period:
        year_s, q_s = period.split("-Q")
        return date(int(year_s), (int(q_s) - 1) * 3 + 1, 1)
    parts = period.split("-")
    if len(parts) == 1:  # "2026" → year
        return date(int(parts[0]), 1, 1)
    if len(parts) == 2:  # "2026-06" → month
        return date(int(parts[0]), int(parts[1]), 1)
    return date.fromisoformat(period)  # "2026-06-08" → day


def _period_end_of_key(period: str) -> date:
    """Last calendar day of the window identified by *period* (format auto-detected).

    Mirrors :func:`_first_day_of_period`; together they give a key's real calendar
    bounds regardless of granularity, so the rollup can decide "has this window
    ended?" without trusting the (now fixed-monthly) window setting.
    """
    start = _first_day_of_period(period)
    if "-W" in period:
        return start + timedelta(days=6)
    if "-Q" in period:  # quarter starts at month 1/4/7/10 → ends two months later
        return _month_end(date(start.year, start.month + 2, 1))
    parts = period.split("-")
    if len(parts) == 1:  # "2026" → year
        return date(start.year, 12, 31)
    if len(parts) == 2:  # "2026-06" → month
        return _month_end(start)
    return start  # "2026-06-08" → day


def _period_ended(period: str, month_start: date) -> bool:
    """True if *period*'s window ends strictly before the current month's first day.

    Defensive against an unparseable key: period keys are always produced by
    :func:`_period_key_for_date` in a known format, so a malformed value can only
    come from external DB corruption. Rather than let it abort the whole rollup
    transaction (and block retention housekeeping), treat it as *not ended* — the
    safest choice, since it leaves the row's state untouched instead of finalising
    or deleting state we can't interpret.
    """
    if not period:
        return False
    try:
        return _period_end_of_key(period) < month_start
    except (ValueError, TypeError):
        logger.warning("Skipping unparseable visitor period key %r during rollup", period)
        return False


def _derived_counts(g: dict[str, Any]) -> dict[str, int]:
    return {
        "unique_visitors": g.get("unique_visitors") or 0,
        "visits": g.get("visits") or 0,
        "bounces": (g.get("closed_bounces") or 0) + (g.get("open_bounces") or 0),
        "total_pageviews": g.get("total_pageviews") or 0,
        "total_duration_s": (g.get("closed_duration") or 0)
        + (g.get("open_duration") or 0)
        + (g.get("open_engaged") or 0),
    }


def _upsert_daily(model: Any, g: dict[str, Any], *, website_id: Any, day: Any) -> None:
    keys = {"website_id": website_id, "day": day, "scope": "site", "scope_value": ""}
    _upsert_counts(model, keys, _derived_counts(g))


def _upsert_period(model: Any, g: dict[str, Any], *, website_id: Any, period_start: Any) -> None:
    keys = {
        "website_id": website_id,
        "period_start": period_start,
        "scope": "site",
        "scope_value": "",
    }
    _upsert_counts(model, keys, _derived_counts(g))


def _upsert_period_counts(
    model: Any,
    *,
    website_id: Any,
    period_start: Any,
    scope: str,
    scope_value: str,
    **vals: int,
) -> None:
    keys = {
        "website_id": website_id,
        "period_start": period_start,
        "scope": scope,
        "scope_value": (scope_value or "")[:500],
    }
    _upsert_counts(model, keys, vals)


def _upsert_counts(model: Any, keys: dict[str, Any], vals: dict[str, int]) -> None:
    """Insert-or-incrementally-add integer counters keyed by *keys*."""
    obj, created = model.objects.get_or_create(**keys, defaults=vals)
    if not created:
        model.objects.filter(pk=obj.pk).update(**{k: F(k) + v for k, v in vals.items()})


def event_visitor_stats(qs: Any) -> dict[str, int]:
    """Sessionise a ``website_event`` queryset into visitor/visit/bounce/duration totals.

    Pure-Python sessioniser (30-min inactivity gap) over ``(visitor_key, created_at)``.
    This is the read-time visitor counter: callers pass a **filtered** pageview
    queryset (any country/device/bot filter applied) and get exact unique visitors,
    sessionised visits, single-pageview bounces and gap-based duration — the
    session-based product's numbers, on the cookieless digest. Returns the five
    count fields.
    """
    from itertools import groupby

    out = {
        "unique_visitors": 0,
        "visits": 0,
        "bounces": 0,
        "total_pageviews": 0,
        "total_duration_s": 0,
    }
    rows = (
        qs.order_by("visitor_key", "created_at").values_list("visitor_key", "created_at").iterator()
    )
    for _key, grp in groupby(rows, key=lambda r: r[0]):
        times = [t for _k, t in grp]
        visits = 1
        visit_pv = 1
        total_dur = 0
        cur_dur = 0
        last = times[0]
        visit_pvs: list[int] = []
        for t in times[1:]:
            gap = max(0, int((t - last).total_seconds()))
            if gap > SESSION_TIMEOUT_S:
                visit_pvs.append(visit_pv)
                total_dur += cur_dur
                visits += 1
                visit_pv = 1
                cur_dur = 0
            else:
                visit_pv += 1
                cur_dur += gap
            last = t
        visit_pvs.append(visit_pv)
        total_dur += cur_dur
        out["unique_visitors"] += 1
        out["visits"] += visits
        out["bounces"] += sum(1 for pv in visit_pvs if pv <= 1)
        out["total_pageviews"] += len(times)
        out["total_duration_s"] += total_dur
    return out


def event_landing_stats(qs: Any) -> dict[str, dict[str, int]]:
    """Sessionise a ``website_event`` queryset into per-entry-page visits/bounces.

    Like :func:`event_visitor_stats` but attributes each sessionised visit to its
    **entry page** (the first pageview of the visit) and tallies single-pageview
    bounces there. Callers pass a **filtered** pageview queryset, so the landing
    table responds to any country/device/bot filter. The gap-based, single-pageview
    bounce rule is used (consistent with the site-level KPIs); the live engaged-time
    refinement does not apply to historical event rows. Returns
    ``{entry_path: {"visits": int, "bounces": int}}``.
    """
    from itertools import groupby

    acc: dict[str, dict[str, int]] = {}

    def _close(entry: str, pv: int) -> None:
        row = acc.setdefault(entry or "/", {"visits": 0, "bounces": 0})
        row["visits"] += 1
        if pv <= 1:
            row["bounces"] += 1

    rows = (
        qs.order_by("visitor_key", "created_at")
        .values_list("visitor_key", "created_at", "url_path")
        .iterator()
    )
    for _key, grp in groupby(rows, key=lambda r: r[0]):
        events = [(t, p) for _k, t, p in grp]
        entry = events[0][1]
        visit_pv = 1
        last = events[0][0]
        for t, p in events[1:]:
            gap = max(0, int((t - last).total_seconds()))
            if gap > SESSION_TIMEOUT_S:
                _close(entry, visit_pv)
                entry = p
                visit_pv = 1
            else:
                visit_pv += 1
            last = t
        _close(entry, visit_pv)
    return acc


# ---------------------------------------------------------------------------
# Small shared helpers (used across the analytics read path).
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
