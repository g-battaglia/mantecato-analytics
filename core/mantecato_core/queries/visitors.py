"""Exact visitor/visit/bounce reads from the compute-and-discard aggregates.

Replaces the former HyperLogLog *estimator*. Values are **exact per day**:
- ``visits``, ``bounces`` (and the derived bounce rate / duration / pages-per-
  visit) are additive and therefore exact for any date range;
- ``visitors`` (unique) is exact per day; over a multi-day range it is the sum
  of daily uniques (a person returning on different days is counted once per
  day — cross-day de-duplication would require a persistent identifier, i.e.
  consent, and is intentionally not done).

Metrics are suppressed (returned as ``None``) when a content/device/geo filter
is active: the aggregates store only counts, not per-row dimensions, so they
cannot be sliced without re-introducing per-person data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Sum

from core.mantecato_core.helpers import compute_derived_stats
from core.mantecato_core.visitor_counting import (
    aggregate_state,
    has_only_bot_filter,
    utc_day,
)

if TYPE_CHECKING:
    from datetime import datetime

# Keys returned (all ``None``) when metrics cannot be computed for the request.
_SUPPRESSED: dict[str, Any] = {
    "visitors": None,
    "visits": None,
    "bounces": None,
    "totaltime": None,
    "bounce_rate": None,
    "avg_duration": None,
    "pages_per_visit": None,
}


def read_visit_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Return exact site-level counts over a date range (day-grained).

    Sums finalized days (``VisitorDaily``) and not-yet-rolled-up days
    (``VisitorDayState``); the two sets are disjoint by day, so there is no
    double counting.
    """
    from apps.core.models import VisitorDaily, VisitorDayState

    start_day = utc_day(start_date)
    end_day = utc_day(end_date)

    daily = VisitorDaily.objects.filter(
        website_id=website_id,
        scope="site",
        scope_value="",
        day__gte=start_day,
        day__lte=end_day,
    ).aggregate(
        unique_visitors=Sum("unique_visitors"),
        visits=Sum("visits"),
        bounces=Sum("bounces"),
        total_pageviews=Sum("total_pageviews"),
        total_duration_s=Sum("total_duration_s"),
    )

    live = aggregate_state(
        VisitorDayState.objects.filter(
            website_id=website_id,
            day__gte=start_day,
            day__lte=end_day,
        )
    )

    return {
        "unique_visitors": (daily["unique_visitors"] or 0) + live["unique_visitors"],
        "visits": (daily["visits"] or 0) + live["visits"],
        "bounces": (daily["bounces"] or 0) + live["bounces"],
        "total_pageviews": (daily["total_pageviews"] or 0) + live["total_pageviews"],
        "total_duration_s": (daily["total_duration_s"] or 0) + live["total_duration_s"],
    }


def visit_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Any] | None = None,
) -> dict[str, Any]:
    """Exact visitor metrics ready to merge into a stats dict.

    Returns ``visitors``, ``visits``, ``bounces``, ``totaltime`` plus the
    derived ``bounce_rate`` / ``avg_duration`` / ``pages_per_visit``. All keys
    are ``None`` when narrowing filters are active (see module docstring).
    """
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
