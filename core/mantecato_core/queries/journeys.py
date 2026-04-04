"""
User journey paths — array_agg per visit with path length limit.
Ported verbatim from src/queries/journeys.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query


async def get_journeys(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    path_length: int = 3,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""WITH visit_pages AS (
      SELECT
        visit_id,
        url_path,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at) AS rn
      FROM website_event
      WHERE website_id = {{{{websiteId::uuid}}}}
        AND created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND event_type = 1
    ),
    visit_journeys AS (
      SELECT
        visit_id,
        array_agg(url_path ORDER BY rn) AS journey
      FROM visit_pages
      WHERE rn <= {path_length}
      GROUP BY visit_id
      HAVING COUNT(*) >= 2
    )
    SELECT
      journey,
      COUNT(*)::bigint AS count
    FROM visit_journeys
    GROUP BY journey
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    total = sum(int(r["count"] or 0) for r in rows)

    return [
        {
            "path": row["journey"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]
