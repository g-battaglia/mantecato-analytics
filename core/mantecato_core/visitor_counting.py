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
from django.db.models import Count, F, Q, Sum
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

    from core.mantecato_core.visitor_writes import fold_visit

    day = utc_day(occurred_at)
    period = _period_key_for_date(day, _window())
    salt = get_or_create_salt(period)
    key = compute_visitor_key(salt, website_id=website_id, ip=ip, user_agent=user_agent)
    fold_visit(
        website_id=website_id,
        day=day,
        period=period,
        key=key,
        occurred_at=occurred_at,
        entry=(url_path or "/")[:500],
        threshold=_bounce_threshold(),
    )
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

    from core.mantecato_core.visitor_writes import fold_engagement

    day = utc_day(occurred_at)
    period = _period_key_for_date(day, _window())
    salt = get_or_create_salt(period)
    key = compute_visitor_key(salt, website_id=website_id, ip=ip, user_agent=user_agent)
    fold_engagement(
        website_id=website_id,
        day=day,
        key=key,
        occurred_at=occurred_at,
        seconds=seconds,
    )


def record_scope_presence(
    *,
    website_id: str,
    occurred_at: datetime,
    visitor_key: str,
    scopes: list[tuple[str, str]],
) -> None:
    """Record that *visitor_key* was seen on each ``(scope, scope_value)`` this window.

    Enables exact per-page/section/group/event unique-visitor counts. Idempotent
    per window via the unique constraint. Skipped for bots (no ``visitor_key``).
    """
    if not visitor_key or not scopes:
        return

    from apps.core.models import VisitorScopeState

    period = _period_key_for_date(utc_day(occurred_at), _window())
    # One pageview can carry many content groups. ``get_or_create`` here used
    # to issue one SELECT (plus an INSERT/transaction for a new row) per scope:
    # 12 groups turned the ingest hot path from 19 into 63 SQL statements.
    # The unique constraint already defines idempotence, so one conflict-
    # ignoring bulk insert has the same semantics in O(1) statements.
    unique_scopes = {(scope, (scope_value or "")[:500]) for scope, scope_value in scopes}
    VisitorScopeState.objects.bulk_create(
        [
            VisitorScopeState(
                website_id=website_id,
                period=period,
                scope=scope,
                scope_value=scope_value,
                visitor_key=visitor_key,
            )
            for scope, scope_value in unique_scopes
        ],
        ignore_conflicts=True,
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
    """Expire event digests in bounded batches; only for offline maintenance."""
    from core.mantecato_core.visitor_rollup import expire_digests

    return expire_digests(now)


def rollup_finished_periods(
    now: datetime | None = None, finished_keys: set[str] | None = None, **options: Any
) -> dict[str, Any]:
    """Offline set-based rollup, committing one finished site/window at a time.

    A non-blocking advisory lock coordinates with imports. Event digests remain
    until the fixed retention cutoff. Never invoke this from an HTTP request.
    """
    from core.mantecato_core.visitor_rollup import run_rollup

    return run_rollup(now, finished_keys=finished_keys, **options)


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
    (nulled rows are skipped on re-run). Pure-Python. Returns
    ``{"days", "events"}``.
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


def _period_bounds_of_key(period: str) -> tuple[date, date]:
    """First and last calendar day of the window identified by *period*.

    The format is auto-detected from the key itself (week ``-W`` / quarter ``-Q`` /
    year / month / day) in a **single** place, so the rollup stays correct even when
    older rows still carry a period key in a granularity that predates the fixed
    monthly window — and the start/end bounds can never drift apart.
    """
    if "-W" in period:
        year_s, week_s = period.split("-W")
        start = date.fromisocalendar(int(year_s), int(week_s), 1)
        return start, start + timedelta(days=6)
    if "-Q" in period:  # quarter starts at month 1/4/7/10 → ends two months later
        year_s, q_s = period.split("-Q")
        start = date(int(year_s), (int(q_s) - 1) * 3 + 1, 1)
        return start, _month_end(date(start.year, start.month + 2, 1))
    parts = period.split("-")
    if len(parts) == 1:  # "2026" → year
        return date(int(parts[0]), 1, 1), date(int(parts[0]), 12, 31)
    if len(parts) == 2:  # "2026-06" → month
        start = date(int(parts[0]), int(parts[1]), 1)
        return start, _month_end(start)
    d = date.fromisoformat(period)  # "2026-06-08" → day
    return d, d


def _first_day_of_period(period: str, window: str | None = None) -> date:
    """First calendar day of the window (format auto-detected from the key).

    ``window`` is accepted for backwards compatibility but ignored.
    """
    return _period_bounds_of_key(period)[0]


def _period_end_of_key(period: str) -> date:
    """Last calendar day of the window identified by *period* (format auto-detected)."""
    return _period_bounds_of_key(period)[1]


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

    PostgreSQL sessioniser (30-min inactivity gap), returning aggregates only.
    This is the read-time visitor counter: callers pass a **filtered** pageview
    queryset (any country/device/bot filter applied) and get exact unique visitors,
    sessionised visits, single-pageview bounces and gap-based duration — the
    session-based product's numbers, on the cookieless digest. Returns the five
    count fields.
    """
    from core.mantecato_core.visitor_reads import session_totals

    return session_totals(qs)


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
    from core.mantecato_core.visitor_reads import session_landings

    return session_landings(qs)


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
