"""
Comparison stats — returns current + previous period metrics via UNION ALL.
Ported verbatim from src/queries/compare.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


async def get_comparison_stats(
    website_id: str,
    current_start: datetime,
    current_end: datetime,
    previous_start: datetime,
    previous_end: datetime,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        """SELECT
      'current' AS period,
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT session_id, visit_id, COUNT(*) AS c,
             MIN(created_at) AS min_time, MAX(created_at) AS max_time
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{currentStart::timestamptz}} AND {{currentEnd::timestamptz}}
        AND event_type = 1
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
      SELECT session_id, visit_id, COUNT(*) AS c,
             MIN(created_at) AS min_time, MAX(created_at) AS max_time
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{previousStart::timestamptz}} AND {{previousEnd::timestamptz}}
        AND event_type = 1
      GROUP BY 1, 2
    ) AS t""",
        {
            "websiteId": website_id,
            "currentStart": current_start,
            "currentEnd": current_end,
            "previousStart": previous_start,
            "previousEnd": previous_end,
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
