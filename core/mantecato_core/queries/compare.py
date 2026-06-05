"""Comparison queries — current vs previous period metrics via UNION ALL.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters


def get_comparison_stats(
    website_id: str,
    current_start: datetime,
    current_end: datetime,
    previous_start: datetime,
    previous_end: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Compute key traffic metrics for two time periods side by side.

    Returns exactly two rows -- one for the ``"current"`` period and
    one for the ``"previous"`` period -- enabling period-over-period
    comparison (e.g. this week vs. last week).  The frontend uses
    these two rows to compute percentage changes and display trend
    arrows.

    Both periods run the same aggregate subquery, combined with
    ``UNION ALL`` so they execute in a single database round-trip.
    Each subquery first groups events by (session_id, visit_id) to
    compute per-visit page counts and durations, then aggregates
    across all visits.

    Bounce detection: a visit is a "bounce" if its page count (``c``)
    equals 1, meaning the visitor saw only a single page.

    Total time is computed by summing ``FLOOR(EXTRACT(EPOCH FROM
    max_time - min_time))`` across all visits, giving the total
    seconds visitors collectively spent on the site.

    Args:
        website_id: UUID of the tracked website.
        current_start: Inclusive start of the current (recent) period.
        current_end: Exclusive end of the current period.
        previous_start: Inclusive start of the comparison (earlier) period.
        previous_end: Exclusive end of the comparison period.
        filters: Optional list of :class:`Filter` objects (incl. the synthetic
            ``__bot_filter__``) applied identically to **both** periods, so the
            comparison columns honour the same bot exclusion / column filters
            as the current period.

    Returns:
        List of exactly two dicts (``"current"`` first, ``"previous"``
        second), each containing:
        - ``period`` (str): ``"current"`` or ``"previous"``.
        - ``pageviews`` (int): Total pageview count.
        - ``visitors`` (int): Unique session count.
        - ``visits`` (int): Unique visit count.
        - ``bounces`` (int): Number of single-page visits.
        - ``totaltime`` (int): Aggregate time on site in seconds.
    """
    # The filter fragment (and any session JOIN it needs) is interpolated
    # into both halves so the bot exclusion / column filters scope the
    # ``current`` and ``previous`` aggregates identically -- mirrors
    # get_website_stats_comparison in queries/stats.py.
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # UNION ALL merges current + previous period in a single query to
    # minimize DB round-trips.  Each half uses a derived table (subquery)
    # that groups by (session_id, visit_id) first, producing per-visit
    # stats (page count 'c', min/max timestamps) before the outer
    # aggregate rolls them up into period-level totals.
    rows = raw_query(
        f"""SELECT
      'current' AS period,
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT we.session_id, we.visit_id, COUNT(*) AS c,
             MIN(we.created_at) AS min_time, MAX(we.created_at) AS max_time
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{currentStart::timestamptz}} AND {{currentEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY 1, 2
    ) AS t
    UNION ALL
    SELECT
      'previous' AS period,
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT we.session_id, we.visit_id, COUNT(*) AS c,
             MIN(we.created_at) AS min_time, MAX(we.created_at) AS max_time
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{previousStart::timestamptz}} AND {{previousEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY 1, 2
    ) AS t""",
        {
            "websiteId": website_id,
            "currentStart": current_start,
            "currentEnd": current_end,
            "previousStart": previous_start,
            "previousEnd": previous_end,
            **filter_params,
        },
    )

    return [
        {
            "period": row["period"],
            "pageviews": int(row["pageviews"] or 0),
            "visitors": int(row["visitors"] or 0),
            "visits": int(row["visits"] or 0),
            "bounces": int(row["bounces"] or 0),
            "totaltime": int(row["totaltime"] or 0),
        }
        for row in rows
    ]
