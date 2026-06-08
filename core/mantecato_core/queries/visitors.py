"""Exact visitor/visit/bounce reads from the compute-and-discard aggregates.

Values are **exact within the configured exactness window**
(``settings.VISITOR_EXACT_WINDOW``, default month):
- ``visits``, ``bounces`` and the derived bounce rate / duration / pages-per-
  visit are additive → exact for any date range;
- ``visitors`` (unique) is exact for any sub-range of the live window, and per
  finalised window; a range spanning several windows sums per-window uniques (a
  person returning in different windows counts once per window — cross-window
  de-duplication needs a persistent identifier, i.e. consent, intentionally not
  done).

Metrics are suppressed (``None``) when a content/device/geo filter is active:
the aggregates store only counts, not per-row dimensions.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import Trunc

from core.mantecato_core.helpers import compute_derived_stats
from core.mantecato_core.visitor_counting import (
    SESSION_TIMEOUT_S,
    aggregate_state,
    current_window,
    current_window_start,
    event_visitor_stats,
    has_only_bot_filter,
    periods_in_range,
    utc_day,
)

_SUPPRESSED: dict[str, Any] = {
    "visitors": None,
    "visits": None,
    "bounces": None,
    "totaltime": None,
    "bounce_rate": None,
    "avg_duration": None,
    "pages_per_visit": None,
}


def _live_behavioral_keys(website_id: str, start_day: Any, end_day: Any) -> set[str]:
    """Behavioural bot digests among live (un-rolled) state in range, computed now.

    Lets the bot-filter toggle drop behavioural bots from the **current** period
    (whose digests are still present) without re-deriving the finalised aggregates.
    Empty when bot detection is disabled for the site.
    """
    from apps.core.models import VisitorDayState
    from core.mantecato_core.bot_sessions import compute_bot_visitor_keys, get_bot_config

    cfg = get_bot_config(website_id)
    if not cfg.get("enabled", False):
        return set()
    engaged: dict[str, float] = {}
    for r in VisitorDayState.objects.filter(
        website_id=website_id, day__gte=start_day, day__lte=end_day
    ).values("visitor_key", "total_duration_s", "cur_page_engaged_s"):
        engaged[r["visitor_key"]] = (
            engaged.get(r["visitor_key"], 0)
            + (r["total_duration_s"] or 0)
            + (r["cur_page_engaged_s"] or 0)
        )
    return compute_bot_visitor_keys(
        website_id,
        datetime.combine(start_day, time.min, tzinfo=UTC),
        datetime.combine(end_day, time.max, tzinfo=UTC),
        cfg,
        engaged_dur_by_key=engaged,
    )


def _unique_visitors(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    bot_filter_on: bool = False,
    behavioral_keys: set[str] | None = None,
) -> int:
    """Exact unique visitors over a range.

    Per exactness window: live ephemeral state if present, else the finalised
    ``VisitorPeriod`` aggregate. The bot filter is a **dynamic toggle**: with it
    **off** the finalised bot uniques are added back; **on** also excludes
    behavioural bots from the live window.
    """
    from apps.core.models import VisitorDayState, VisitorPeriod

    behavioral_keys = behavioral_keys or set()
    start_day = utc_day(start_date)
    end_day = utc_day(end_date)
    total = 0
    for pk, p_start, p_end in periods_in_range(start_day, end_day, current_window()):
        ov_start = max(start_day, p_start)
        ov_end = min(end_day, p_end)
        base = VisitorDayState.objects.filter(
            website_id=website_id, period=pk, day__gte=ov_start, day__lte=ov_end
        )
        if base.exists():
            live_qs = base.exclude(visitor_key__in=behavioral_keys) if (
                bot_filter_on and behavioral_keys
            ) else base
            total += live_qs.values("visitor_key").distinct().count()
        else:
            row = VisitorPeriod.objects.filter(
                website_id=website_id, period_start=p_start, scope="site", scope_value=""
            ).first()
            if row:
                total += row.unique_visitors + (0 if bot_filter_on else row.bot_unique_visitors)
    return total


def read_visit_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    bot_filter_on: bool = False,
) -> dict[str, int]:
    """Return exact site-level counts over a date range.

    Combines live ephemeral state (un-rolled days) with the finalised
    ``VisitorDaily`` aggregates, excluding days that still have live state (each
    day counted once). The bot filter is a **dynamic toggle**: with it **off** the
    ``bot_*`` aggregate columns are added back; **on** also drops behavioural bots
    from the live window.
    """
    from apps.core.models import VisitorDaily, VisitorDayState

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)

    live_days = set(
        VisitorDayState.objects.filter(
            website_id=website_id, day__gte=start_day, day__lte=end_day
        )
        .values_list("day", flat=True)
        .distinct()
    )
    behavioral = _live_behavioral_keys(website_id, start_day, end_day) if bot_filter_on else set()
    live_qs = VisitorDayState.objects.filter(
        website_id=website_id, day__gte=start_day, day__lte=end_day
    )
    if behavioral:
        live_qs = live_qs.exclude(visitor_key__in=behavioral)
    live = aggregate_state(live_qs)

    fields: dict[str, Any] = {
        "visits": Sum("visits"),
        "bounces": Sum("bounces"),
        "total_pageviews": Sum("total_pageviews"),
        "total_duration_s": Sum("total_duration_s"),
    }
    if not bot_filter_on:
        fields.update(
            {
                "bot_visits": Sum("bot_visits"),
                "bot_bounces": Sum("bot_bounces"),
                "bot_total_pageviews": Sum("bot_total_pageviews"),
                "bot_total_duration_s": Sum("bot_total_duration_s"),
            }
        )
    daily = (
        VisitorDaily.objects.filter(
            website_id=website_id,
            scope="site",
            scope_value="",
            day__gte=start_day,
            day__lte=end_day,
        )
        .exclude(day__in=live_days)
        .aggregate(**fields)
    )

    def _final(human: str, bot: str) -> int:
        val = daily.get(human) or 0
        if not bot_filter_on:
            val += daily.get(bot) or 0
        return val

    result = {
        "unique_visitors": _unique_visitors(
            website_id,
            start_date,
            end_date,
            bot_filter_on=bot_filter_on,
            behavioral_keys=behavioral,
        ),
        "visits": _final("visits", "bot_visits") + live["visits"],
        "bounces": _final("bounces", "bot_bounces") + live["bounces"],
        "total_pageviews": _final("total_pageviews", "bot_total_pageviews")
        + live["total_pageviews"],
        "total_duration_s": _final("total_duration_s", "bot_total_duration_s")
        + live["total_duration_s"],
    }

    # Current-period UA/datacentre bots (is_bot) aren't in VisitorDayState and aren't
    # rolled into bot_* yet. With the filter OFF, count them from the events so the
    # toggle moves visitors on live data too (not only after the rollup).
    if not bot_filter_on:
        from apps.core.models import WebsiteEvent

        live_start = max(
            start_date, datetime.combine(current_window_start(), time.min, tzinfo=UTC)
        )
        isb = event_visitor_stats(
            WebsiteEvent.objects.filter(
                website_id=website_id,
                event_type=1,
                is_bot=True,
                visitor_key__isnull=False,
                created_at__gte=live_start,
                created_at__lte=end_date,
            )
        )
        result["unique_visitors"] += isb["unique_visitors"]
        result["visits"] += isb["visits"]
        result["bounces"] += isb["bounces"]
        result["total_pageviews"] += isb["total_pageviews"]
        result["total_duration_s"] += isb["total_duration_s"]
    return result


def read_scope_visitors(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    scope: str,
    scope_values: list[str],
) -> dict[str, int]:
    """Return exact unique visitors per ``scope_value`` for the window(s) in range.

    Per-scope counts are window-grained: for a range inside the live window they
    reflect that window's uniques per value (exact for the window, not for an
    arbitrary sub-range). Returns ``{scope_value: count}``.
    """
    if not scope_values:
        return {}
    from apps.core.models import VisitorPeriod, VisitorScopeState

    out: dict[str, int] = {v: 0 for v in scope_values}
    spans = periods_in_range(utc_day(start_date), utc_day(end_date), current_window())
    for pk, p_start, _p_end in spans:
        live = (
            VisitorScopeState.objects.filter(
                website_id=website_id, period=pk, scope=scope, scope_value__in=scope_values
            )
            .values("scope_value")
            .annotate(n=Count("visitor_key", distinct=True))
        )
        live_rows = list(live)
        if live_rows:
            for r in live_rows:
                out[r["scope_value"]] = out.get(r["scope_value"], 0) + (r["n"] or 0)
        else:
            for r in VisitorPeriod.objects.filter(
                website_id=website_id,
                period_start=p_start,
                scope=scope,
                scope_value__in=scope_values,
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
    """Entry (landing) pages with visits, bounces and bounce rate.

    Combines live ephemeral state (un-rolled periods, from ``VisitorDayState``
    grouped by ``entry_path``) with finalised ``VisitorPeriod`` landing aggregates,
    per period (live if present, else finalised) so each period is counted once.
    Bounces use the engaged definition. Suppressed (``[]``) under a content/
    device/geo filter — landing aggregates can't be sliced by those dimensions.
    """
    if not has_only_bot_filter(filters):
        return []
    from apps.core.models import VisitorDayState, VisitorPeriod
    from core.mantecato_core.visitor_counting import _bounce_threshold, _open_bounce_filter

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)
    threshold = _bounce_threshold()
    acc: dict[str, dict[str, int]] = {}

    def _add(entry: str | None, visits: int, bounces: int) -> None:
        row = acc.setdefault(entry or "/", {"visits": 0, "bounces": 0})
        row["visits"] += visits
        row["bounces"] += bounces

    for pk, p_start, _p_end in periods_in_range(start_day, end_day, current_window()):
        live = list(
            VisitorDayState.objects.filter(website_id=website_id, period=pk)
            .exclude(entry_path__isnull=True)
            .values("entry_path")
            .annotate(
                visits=Count("id"),
                bounces=Count("id", filter=_open_bounce_filter(threshold)),
            )
        )
        if live:
            for r in live:
                _add(r["entry_path"], r["visits"] or 0, r["bounces"] or 0)
        else:
            for r in VisitorPeriod.objects.filter(
                website_id=website_id, period_start=p_start, scope="landing"
            ).values("scope_value", "visits", "bounces"):
                _add(r["scope_value"], r["visits"] or 0, r["bounces"] or 0)

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
) -> dict[str, int]:
    """Return ``{bucket_iso: unique_visitors}`` for the time series, **any granularity**.

    Exact unique visitors per bucket (including per hour) come from the per-event
    window-salted digest on ``website_event`` — so the Visitors line is always
    available, even at hourly resolution. Buckets are truncated in UTC to match
    the pageview series. Finalised windows (digests NULLed at rollup) contribute
    nothing here; the chart range is normally recent (live) data.
    """
    from apps.core.models import WebsiteEvent

    gran = granularity if granularity in _GRANULARITIES else "day"
    rows = (
        WebsiteEvent.objects.filter(
            website_id=website_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
            event_type=1,
            is_bot=False,
            visitor_key__isnull=False,
        )
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
) -> dict[str, int]:
    """Return ``{bucket_iso: visits}`` bucketed by each visit's start, **any granularity**.

    Visits are sessionised (30-min inactivity gap) from the per-event window
    digests on ``website_event`` and each visit is attributed to the bucket of its
    first pageview. The bucket truncation matches :func:`visitors_by_bucket` (same
    ``Trunc`` in UTC) so keys align with the pageview/visitors series. Finalised
    buckets (digests NULLed at rollup) contribute nothing — like the Visitors line,
    the chart range is normally recent (live) data.
    """
    from itertools import groupby

    from apps.core.models import WebsiteEvent

    gran = granularity if granularity in _GRANULARITIES else "day"
    rows = (
        WebsiteEvent.objects.filter(
            website_id=website_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
            event_type=1,
            is_bot=False,
            visitor_key__isnull=False,
        )
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
    """Exact visitor metrics ready to merge into a stats dict (``None`` when filtered)."""
    if not has_only_bot_filter(filters):
        return dict(_SUPPRESSED)

    # The bot-filter toggle (``__bot_filter__`` present) excludes bots dynamically;
    # without it the bot counts are included (same data, filter just hides them).
    bot_on = any(getattr(f, "column", "") == "__bot_filter__" for f in (filters or []))
    vs = read_visit_stats(website_id, start_date, end_date, bot_filter_on=bot_on)
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
