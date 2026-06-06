"""Geographic breakdown queries — aggregate pageviews by country.

Privacy-first: only country-level aggregation. Region/city removed to
prevent re-identification of individuals in low-traffic scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, build_filter_sql


def get_geo_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate pageview counts by country (ISO 3166-1 alpha-2)."""
    filters = filters or []

    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
    }

    rows = raw_query(
        """SELECT
      we.country AS country,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {websiteId::uuid}
      AND we.created_at BETWEEN {startDate::timestamptz} AND {endDate::timestamptz}
      AND we.event_type = 1
      AND we.country IS NOT NULL
      AND we.country != ''
    GROUP BY we.country
    ORDER BY pageviews DESC
    LIMIT """ + str(limit),
        params,
    )

    total = sum(int(r["pageviews"] or 0) for r in rows)

    return [
        {
            "country": row["country"],
            "pageviews": int(row["pageviews"] or 0),
            "percentage": round((int(row["pageviews"] or 0) / total) * 100, 1) if total > 0 else 0,
        }
        for row in rows
    ]
