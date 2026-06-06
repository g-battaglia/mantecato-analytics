"""Comparison queries — aggregate pageview comparison between two periods.

Privacy-first: only pageview counts are compared. No visitor/session metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter


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
    rows = raw_query(
        """SELECT 'current' AS period,
      COUNT(*)::bigint AS pageviews
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
      AND event_type = 1
    UNION ALL
    SELECT 'previous' AS period,
      COUNT(*)::bigint AS pageviews
    FROM website_event
    WHERE website_id = {{websiteId::uuid}}
      AND created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
      AND event_type = 1""",
        {
            "websiteId": website_id,
            "curStart": cur_start,
            "curEnd": cur_end,
            "prevStart": prev_start,
            "prevEnd": prev_end,
        },
    )
    return [
        {"period": row["period"], "pageviews": int(row.get("pageviews") or 0)}
        for row in rows
    ]
