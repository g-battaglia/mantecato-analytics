"""Comparison queries — aggregate pageview comparison between two periods.

Privacy-first: only pageview counts are compared. No visitor/session metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters
from core.mantecato_core.queries.orm_fallbacks import (
    pageview_queryset,
    should_use_orm_fallback,
    stats_dict,
)


def get_comparison_stats(
    website_id: str,
    cur_start: datetime,
    cur_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return pageview counts for two periods for comparison.

    Returns ``[{"period": "current", "pageviews": N}, {"period": "previous", "pageviews": N}]``.
    """
    if should_use_orm_fallback():
        return [
            {"period": "current", **stats_dict(pageview_queryset(website_id, cur_start, cur_end, filters))},
            {"period": "previous", **stats_dict(pageview_queryset(website_id, prev_start, prev_end, filters))},
        ]

    filter_where, filter_params, _ = prepare_filters(filters or [])
    rows = raw_query(
        """SELECT 'current' AS period,
      COUNT(*)::bigint AS pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = false)::bigint AS human_pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = true)::bigint AS bot_pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
      AND we.event_type = 1
      """ + filter_where + """
    UNION ALL
    SELECT 'previous' AS period,
      COUNT(*)::bigint AS pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = false)::bigint AS human_pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = true)::bigint AS bot_pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
      AND we.event_type = 1
      """ + filter_where,
        {
            "websiteId": website_id,
            "curStart": cur_start,
            "curEnd": cur_end,
            "prevStart": prev_start,
            "prevEnd": prev_end,
            **filter_params,
        },
    )
    return [
        {
            "period": row["period"],
            "pageviews": int(row.get("pageviews") or 0),
            "human_pageviews": int(row.get("human_pageviews") or 0),
            "bot_pageviews": int(row.get("bot_pageviews") or 0),
        }
        for row in rows
    ]
