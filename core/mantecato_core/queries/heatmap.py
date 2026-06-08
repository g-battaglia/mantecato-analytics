"""Traffic heatmap — pageviews grouped by day-of-week and hour-of-day.

Privacy-first: only aggregate pageview counts, no visitor metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters
from core.mantecato_core.queries.orm_fallbacks import (
    heatmap_rows,
    pageview_queryset,
    should_use_orm_fallback,
)


def get_traffic_heatmap(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return pageview counts for each (day_of_week, hour) bucket.

    day_of_week: 0=Sunday, 1=Monday, ... 6=Saturday (PostgreSQL DOW).
    hour: 0-23.
    """
    if should_use_orm_fallback():
        return heatmap_rows(pageview_queryset(website_id, start_date, end_date, filters))

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

    rows = raw_query(
        """SELECT
      EXTRACT(DOW FROM we.created_at)::int AS day_of_week,
      EXTRACT(HOUR FROM we.created_at)::int AS hour,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      """ + filter_where + """
    GROUP BY 1, 2
    ORDER BY 1, 2""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "dayOfWeek": int(row["day_of_week"]),
            "hour": int(row["hour"]),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]
