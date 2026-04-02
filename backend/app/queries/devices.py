from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query
from ..filters import Filter, build_filter_sql


async def get_device_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    dimension: str,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    valid_dimensions = ["browser", "os", "device", "screen", "language"]
    if dimension not in valid_dimensions:
        return []
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    rows = await raw_query(
        f"""SELECT
      s.{dimension} AS value,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.{dimension} IS NOT NULL
      AND s.{dimension} != ''
      {filter_where}
    GROUP BY s.{dimension}
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    total = sum(int(r["visitors"] or 0) for r in rows)

    return [
        {
            "value": row["value"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "percentage": (int(row["visitors"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]
