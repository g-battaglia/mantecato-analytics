"""Exact visitor/visit/bounce reads — computed **at read time** from event digests.

Unique visitors, sessionised visits, single-pageview bounces and gap-based
duration are derived from the per-event window digest (``website_event.visitor_key``)
each request, exactly like the session-based product but on a cookieless token.

Because the count is computed from the (filtered) event rows, **every filter
applies downstream** — country, device, URL and the bot filter all slice the
visitor metrics; nothing is baked into stored data. This holds for the site-level
KPIs, the time-series, the per-page / per-section / per-event breakdowns and the
landing-page table alike. Exact within the digest retention window
(``settings.VISITOR_KEY_RETENTION_DAYS``, ~13 months); ranges reaching past it
fold in the permanent anonymous aggregates (which, being dimensionless, are not
filterable). Cross-window de-duplication is intentionally not done (it would need
a persistent identifier, i.e. consent).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import Trunc
from django.utils import timezone

from core.mantecato_core.helpers import compute_derived_stats
from core.mantecato_core.visitor_counting import (
    SESSION_TIMEOUT_S,
    _period_bounds,
    current_window,
    event_landing_stats,
    event_visitor_stats,
    has_only_bot_filter,
    periods_in_range,
    section_for_path,
    utc_day,
)


def _retention_split(window: str) -> tuple[date, datetime]:
    """Window-aligned boundary between the live event path and stored aggregates.

    Events on or before the retention cutoff have digests the rollup is
    progressively NULLing, yet are already captured exactly by the permanent
    aggregates. Splitting at the *window* boundary that contains the cutoff
    avoids both a gap (nulled-key events counted nowhere) and a double count (the
    straddling window's whole-window aggregate overlapping live events):
    aggregates cover up to and including that window; the event path starts at
    the next one. For the default ``window="day"`` the split is exactly the day
    after the cutoff day. Returns ``(agg_upper_day, event_lower)``.
    """
    from django.conf import settings as dj_settings

    retention = int(getattr(dj_settings, "VISITOR_KEY_RETENTION_DAYS", 396))
    boundary_day = utc_day(timezone.now() - timedelta(days=retention))
    _, agg_upper_day = _period_bounds(boundary_day, window)
    event_lower = datetime(
        agg_upper_day.year, agg_upper_day.month, agg_upper_day.day, tzinfo=UTC
    ) + timedelta(days=1)
    return agg_upper_day, event_lower


def read_visit_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Any] | None = None,
) -> dict[str, int]:
    """Exact site-level visitor/visit/bounce/duration over a range — **filterable**.

    Computed at read time from the per-event window digests (``visitor_key``),
    sessionised (30-min inactivity gap) into visits, so **any** filter (country,
    device, bot rules) applies downstream like the session-based product — within
    the digest retention window (``VISITOR_KEY_RETENTION_DAYS``, ~13 months). Older
    data, whose digests the rollup has discarded, reads the permanent anonymous
    daily aggregates (which cannot be filtered).
    """
    from apps.core.models import VisitorDaily
    from core.mantecato_core.queries.orm_fallbacks import pageview_queryset

    agg_upper_day, event_lower = _retention_split(current_window())

    # Within retention: exact and filterable, straight from the event digests.
    ev_qs = pageview_queryset(website_id, max(start_date, event_lower), end_date, filters).filter(
        visitor_key__isnull=False
    )
    stats = event_visitor_stats(ev_qs)

    # Beyond retention: anonymous daily aggregates (cannot be sliced by a filter).
    # Upper-bounded by the requested end so a fully-historical range isn't summed
    # all the way to the retention edge.
    if start_date < event_lower:
        agg = VisitorDaily.objects.filter(
            website_id=website_id,
            scope="site",
            scope_value="",
            day__gte=utc_day(start_date),
            day__lte=min(agg_upper_day, utc_day(end_date)),
        ).aggregate(
            u=Sum("unique_visitors"),
            v=Sum("visits"),
            b=Sum("bounces"),
            p=Sum("total_pageviews"),
            d=Sum("total_duration_s"),
        )
        stats["unique_visitors"] += agg["u"] or 0
        stats["visits"] += agg["v"] or 0
        stats["bounces"] += agg["b"] or 0
        stats["total_pageviews"] += agg["p"] or 0
        stats["total_duration_s"] += agg["d"] or 0
    return stats


def read_scope_visitors(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    scope: str,
    scope_values: list[str],
    filters: list[Any] | None = None,
) -> dict[str, int]:
    """Return exact unique visitors per ``scope_value`` — **filterable** at read time.

    Computed from the per-event window digests (``visitor_key``) for ``page`` /
    ``section`` (pageviews) and ``event`` (custom events), so a country/device/bot
    filter slices them downstream — the dimensionless aggregates couldn't. Exact
    within the digest retention window; the portion of the range beyond retention
    folds in the permanent ``VisitorPeriod`` aggregates (only when no content
    filter narrows the population — they can't be sliced). Returns
    ``{scope_value: count}``.
    """
    if not scope_values:
        return {}
    from collections import defaultdict

    from apps.core.models import VisitorPeriod
    from core.mantecato_core.queries.orm_fallbacks import (
        custom_event_queryset,
        pageview_queryset,
    )

    window = current_window()
    agg_upper_day, event_lower = _retention_split(window)
    want = set(scope_values)
    out: dict[str, int] = {v: 0 for v in scope_values}

    # Within retention: exact and filterable, straight from the event digests.
    qs_factory = custom_event_queryset if scope == "event" else pageview_queryset
    ev_qs = qs_factory(website_id, max(start_date, event_lower), end_date, filters).filter(
        visitor_key__isnull=False
    )
    if scope == "section":
        from core.mantecato_core.queries.stats import _normalize_url

        seen: dict[str, set[str]] = defaultdict(set)
        for url_path, vkey in ev_qs.values_list("url_path", "visitor_key").iterator():
            sec = _normalize_url(section_for_path(url_path or "/"), "smart")
            if sec in want:
                seen[sec].add(vkey)
        for sec, keys in seen.items():
            out[sec] = len(keys)
    else:
        field = "event_name" if scope == "event" else "url_path"
        rows = (
            ev_qs.filter(**{f"{field}__in": list(want)})
            .values(field)
            .annotate(n=Count("visitor_key", distinct=True))
        )
        for r in rows:
            out[r[field]] = r["n"] or 0

    # Beyond retention: dimensionless aggregates (cannot be sliced by a filter).
    if start_date < event_lower and has_only_bot_filter(filters):
        for _pk, p_start, _p_end in periods_in_range(
            utc_day(start_date), min(agg_upper_day, utc_day(end_date)), window
        ):
            for r in VisitorPeriod.objects.filter(
                website_id=website_id,
                period_start=p_start,
                scope=scope,
                scope_value__in=list(want),
            ).values("scope_value", "unique_visitors"):
                out[r["scope_value"]] = out.get(r["scope_value"], 0) + (r["unique_visitors"] or 0)
    return out


def get_landing_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Entry (landing) pages with visits, bounces and bounce rate — **filterable**.

    Sessionises the (filtered) per-event digests at read time and attributes each
    visit to its entry page, so a country/device/bot filter slices the landing
    table downstream like the session-based product. Within the digest retention
    window; the portion of the range beyond retention folds in the finalised
    ``VisitorPeriod`` landing aggregates (only when no content filter narrows the
    population — they can't be sliced). Single-pageview (gap-based) bounce rule,
    consistent with the site-level KPIs.
    """
    from apps.core.models import VisitorPeriod
    from core.mantecato_core.queries.orm_fallbacks import pageview_queryset

    window = current_window()
    agg_upper_day, event_lower = _retention_split(window)

    def _add(acc: dict[str, dict[str, int]], entry: str | None, visits: int, bounces: int) -> None:
        row = acc.setdefault(entry or "/", {"visits": 0, "bounces": 0})
        row["visits"] += visits
        row["bounces"] += bounces

    # Within retention: from the (filtered) event digests, sessionised per visit.
    ev_qs = pageview_queryset(website_id, max(start_date, event_lower), end_date, filters).filter(
        visitor_key__isnull=False
    )
    acc = event_landing_stats(ev_qs)

    # Beyond retention: finalised landing aggregates (cannot be sliced by a filter).
    if start_date < event_lower and has_only_bot_filter(filters):
        for _pk, p_start, _p_end in periods_in_range(
            utc_day(start_date), min(agg_upper_day, utc_day(end_date)), window
        ):
            for r in VisitorPeriod.objects.filter(
                website_id=website_id, period_start=p_start, scope="landing"
            ).values("scope_value", "visits", "bounces"):
                _add(acc, r["scope_value"], r["visits"] or 0, r["bounces"] or 0)

    rows = [
        {
            "entry_path": entry,
            "visits": v["visits"],
            "bounces": v["bounces"],
            "bounce_rate": round((v["bounces"] / v["visits"]) * 100, 1) if v["visits"] else 0.0,
        }
        for entry, v in acc.items()
    ]
    rows.sort(key=lambda r: (-r["visits"], r["entry_path"]))
    return rows[:limit]


_GRANULARITIES = ("minute", "hour", "day", "week", "month")


def visitors_by_bucket(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Any] | None = None,
) -> dict[str, int]:
    """Return ``{bucket_iso: unique_visitors}`` for the time series, **any granularity**.

    Exact unique visitors per bucket (including per hour) come from the per-event
    window digest on ``website_event``, with the active **filters** applied (so the
    Visitors line responds to the bot/country/device filter). Buckets are truncated
    in UTC to match the pageview series. Digests discarded past retention contribute
    nothing here; the chart range is normally within retention.

    Each bucket is a *per-bucket* unique count: with the monthly dedup window a
    visitor active on several days is one device per day, so the buckets do **not**
    sum to the monthly-unique KPI (a returning visitor is counted once there). This
    is the same daily-uniques-vs-period-total relationship Plausible/Fathom show; the
    KPI card carries a "Deduplicated within each month" note for multi-month ranges.
    """
    from core.mantecato_core.queries.orm_fallbacks import pageview_queryset

    gran = granularity if granularity in _GRANULARITIES else "day"
    rows = (
        pageview_queryset(website_id, start_date, end_date, filters)
        .filter(visitor_key__isnull=False)
        .annotate(bucket=Trunc("created_at", gran, tzinfo=UTC))
        .values("bucket")
        .annotate(v=Count("visitor_key", distinct=True))
    )
    out: dict[str, int] = {}
    for r in rows:
        bucket = r["bucket"]
        key = bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket)
        out[key] = r["v"] or 0
    return out


def visits_by_bucket(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Any] | None = None,
) -> dict[str, int]:
    """Return ``{bucket_iso: visits}`` bucketed by each visit's start, **any granularity**.

    Visits are sessionised (30-min inactivity gap) from the per-event window digests
    on ``website_event`` (with the active **filters** applied) and each visit is
    attributed to the bucket of its first pageview. The bucket truncation matches
    :func:`visitors_by_bucket` so keys align with the pageview/visitors series.
    """
    from itertools import groupby

    from apps.core.models import WebsiteEvent
    from core.mantecato_core.queries.orm_fallbacks import pageview_queryset

    gran = granularity if granularity in _GRANULARITIES else "day"
    rows = (
        pageview_queryset(website_id, start_date, end_date, filters)
        .filter(visitor_key__isnull=False)
        .order_by("visitor_key", "created_at")
        .values_list("event_id", "visitor_key", "created_at")
        .iterator()
    )
    start_ids: list[Any] = []
    for _key, grp in groupby(rows, key=lambda r: r[1]):
        last = None
        for event_id, _k, created_at in grp:
            if last is None or (created_at - last).total_seconds() > SESSION_TIMEOUT_S:
                start_ids.append(event_id)
            last = created_at
    if not start_ids:
        return {}

    agg = (
        WebsiteEvent.objects.filter(event_id__in=start_ids)
        .annotate(bucket=Trunc("created_at", gran, tzinfo=UTC))
        .values("bucket")
        .annotate(v=Count("event_id"))
    )
    out: dict[str, int] = {}
    for r in agg:
        bucket = r["bucket"]
        key = bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket)
        out[key] = r["v"] or 0
    return out


def visit_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Any] | None = None,
) -> dict[str, Any]:
    """Exact visitor metrics ready to merge into a stats dict.

    Fully **filterable**: the bot filter and any content/device/geo filter apply at
    read time (downstream), and never change what is stored. Exact within the digest
    retention window; older data folds in the anonymous aggregates.
    """
    vs = read_visit_stats(website_id, start_date, end_date, filters)
    derived = compute_derived_stats(
        {
            "pageviews": vs["total_pageviews"],
            "visits": vs["visits"],
            "bounces": vs["bounces"],
            "totaltime": vs["total_duration_s"],
        }
    )
    return {
        "visitors": vs["unique_visitors"],
        "visits": vs["visits"],
        "bounces": vs["bounces"],
        "totaltime": vs["total_duration_s"],
        "bounce_rate": derived["bounce_rate"],
        "avg_duration": derived["avg_duration"],
        "pages_per_visit": derived["pages_per_visit"],
    }
