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

from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Sum

from core.mantecato_core.helpers import compute_derived_stats
from core.mantecato_core.visitor_counting import (
    aggregate_state,
    current_period_key,
    current_window,
    current_window_start,
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
    """Exact unique visitors over a range (distinct on live window + finalised windows)."""
    from apps.core.models import VisitorDayState, VisitorPeriod

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)
    cur = current_period_key()
    total = 0
    for pk, p_start, p_end in periods_in_range(start_day, end_day, current_window()):
        if pk == cur:
            ov_start = max(start_day, p_start)
            ov_end = min(end_day, p_end)
            total += (
                VisitorDayState.objects.filter(
                    website_id=website_id,
                    period=cur,
                    day__gte=ov_start,
                    day__lte=ov_end,
                )
                .values("visitor_key")
                .distinct()
                .count()
            )
        else:
            row = VisitorPeriod.objects.filter(
                website_id=website_id,
                period_start=p_start,
                scope="site",
                scope_value="",
            ).first()
            total += row.unique_visitors if row else 0
    return total


def read_visit_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Return exact site-level counts over a date range."""
    from apps.core.models import VisitorDaily, VisitorDayState

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)

    # Additive metrics: finalised per-day aggregates (days strictly before the
    # current window) + the live state (current window). Splitting on the window
    # boundary guarantees each day is counted once (no VisitorDaily/VisitorDayState
    # overlap → visits never exceed pageviews).
    window_start = current_window_start()
    daily = VisitorDaily.objects.filter(
        website_id=website_id,
        scope="site",
        scope_value="",
        day__gte=start_day,
        day__lte=end_day,
        day__lt=window_start,
    ).aggregate(
        visits=Sum("visits"),
        bounces=Sum("bounces"),
        total_pageviews=Sum("total_pageviews"),
        total_duration_s=Sum("total_duration_s"),
    )
    live = aggregate_state(
        VisitorDayState.objects.filter(
            website_id=website_id,
            day__gte=max(start_day, window_start),
            day__lte=end_day,
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

    cur = current_period_key()
    out: dict[str, int] = {v: 0 for v in scope_values}
    spans = periods_in_range(utc_day(start_date), utc_day(end_date), current_window())
    for pk, p_start, _p_end in spans:
        if pk == cur:
            rows = (
                VisitorScopeState.objects.filter(
                    website_id=website_id,
                    period=cur,
                    scope=scope,
                    scope_value__in=scope_values,
                )
                .values("scope_value")
                .annotate(n=Count("visitor_key", distinct=True))
            )
            for r in rows:
                out[r["scope_value"]] = out.get(r["scope_value"], 0) + (r["n"] or 0)
        else:
            rows = VisitorPeriod.objects.filter(
                website_id=website_id,
                period_start=p_start,
                scope=scope,
                scope_value__in=scope_values,
            ).values("scope_value", "unique_visitors")
            for r in rows:
                out[r["scope_value"]] = out.get(r["scope_value"], 0) + (r["unique_visitors"] or 0)
    return out


def _bucket_date(d: Any, granularity: str) -> Any:
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    if granularity == "month":
        return d.replace(day=1)
    return d


def visits_by_bucket(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
) -> dict[Any, int]:
    """Return ``{bucket_start_date: visits}`` for a time series.

    Visits are a daily metric, so this is only meaningful at day/week/month
    granularity; finer granularities return ``{}`` (no Visits line is drawn).
    Combines finalised per-day aggregates with the live (current-window) state.
    """
    if granularity not in ("day", "week", "month"):
        return {}
    from apps.core.models import VisitorDaily, VisitorDayState

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)
    window_start = current_window_start()
    out: dict[Any, int] = defaultdict(int)
    # Finalised days from VisitorDaily; current-window days from live state —
    # split on the window boundary so no day is double-counted.
    for r in VisitorDaily.objects.filter(
        website_id=website_id,
        scope="site",
        scope_value="",
        day__gte=start_day,
        day__lte=end_day,
        day__lt=window_start,
    ).values("day", "visits"):
        out[_bucket_date(r["day"], granularity)] += r["visits"] or 0
    for r in (
        VisitorDayState.objects.filter(
            website_id=website_id, day__gte=max(start_day, window_start), day__lte=end_day
        )
        .values("day")
        .annotate(v=Sum("visits"))
    ):
        out[_bucket_date(r["day"], granularity)] += r["v"] or 0
    return dict(out)


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
