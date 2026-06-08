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

from datetime import UTC
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Sum
from django.db.models.functions import Trunc

from core.mantecato_core.helpers import compute_derived_stats
from core.mantecato_core.visitor_counting import (
    SESSION_TIMEOUT_S,
    aggregate_state,
    current_window,
    has_only_bot_filter,
    periods_in_range,
    utc_day,
)

if TYPE_CHECKING:
    from datetime import datetime

_SUPPRESSED: dict[str, Any] = {
    "visitors": None,
    "visits": None,
    "bounces": None,
    "totaltime": None,
    "bounce_rate": None,
    "avg_duration": None,
    "pages_per_visit": None,
}


def _unique_visitors(website_id: str, start_date: datetime, end_date: datetime) -> int:
    """Exact unique visitors over a range.

    Per exactness window: if live ephemeral state exists for the window (not yet
    rolled up) use its distinct digest count; otherwise use the finalised
    ``VisitorPeriod`` aggregate. With a day window each day is a window, so the
    total is the sum of daily uniques (Umami-aligned).
    """
    from apps.core.models import VisitorDayState, VisitorPeriod

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)
    total = 0
    for pk, p_start, p_end in periods_in_range(start_day, end_day, current_window()):
        ov_start = max(start_day, p_start)
        ov_end = min(end_day, p_end)
        live_count = (
            VisitorDayState.objects.filter(
                website_id=website_id, period=pk, day__gte=ov_start, day__lte=ov_end
            )
            .values("visitor_key")
            .distinct()
            .count()
        )
        if live_count:
            total += live_count
        else:
            row = VisitorPeriod.objects.filter(
                website_id=website_id, period_start=p_start, scope="site", scope_value=""
            ).first()
            total += row.unique_visitors if row else 0
    return total


def read_visit_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Return exact site-level counts over a date range.

    Additive metrics combine live ephemeral state (un-rolled days) with the
    finalised ``VisitorDaily`` aggregates, **excluding days that still have live
    state** so each day is counted exactly once (no double counting, visits never
    exceed pageviews).
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
    live = aggregate_state(
        VisitorDayState.objects.filter(
            website_id=website_id, day__gte=start_day, day__lte=end_day
        )
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
        .aggregate(
            visits=Sum("visits"),
            bounces=Sum("bounces"),
            total_pageviews=Sum("total_pageviews"),
            total_duration_s=Sum("total_duration_s"),
        )
    )

    return {
        "unique_visitors": _unique_visitors(website_id, start_date, end_date),
        "visits": (daily["visits"] or 0) + live["visits"],
        "bounces": (daily["bounces"] or 0) + live["bounces"],
        "total_pageviews": (daily["total_pageviews"] or 0) + live["total_pageviews"],
        "total_duration_s": (daily["total_duration_s"] or 0) + live["total_duration_s"],
    }


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

    vs = read_visit_stats(website_id, start_date, end_date)
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
