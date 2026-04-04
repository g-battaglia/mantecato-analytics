"""
Geographic breakdown queries — country / region / city with bounce rate
and average visit duration.  Ported verbatim from src/queries/geo.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query
from mantecato_core.filters import Filter, build_filter_sql


async def get_geo_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    level: str = "country",
    country_filter: str | None = None,
    region_filter: str | None = None,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
        **filter_params,
    }

    # Build inner/outer GROUP BY and SELECT expressions based on level
    if level == "city":
        inner_group_by = "s.country, s.region, s.city"
        outer_group_by = "country, region, city"
        outer_select_geo = "country, region, city,"
    elif level == "region":
        inner_group_by = "s.country, s.region"
        outer_group_by = "country, region"
        outer_select_geo = "country, region, NULL AS city,"
    else:
        inner_group_by = "s.country"
        outer_group_by = "country"
        outer_select_geo = "country, NULL AS region, NULL AS city,"

    # Additional filters for drill-down
    extra_filter = ""
    if country_filter and level in ("region", "city"):
        extra_filter += " AND s.country = {{countryFilter}}"
        params["countryFilter"] = country_filter
    if region_filter and level == "city":
        extra_filter += " AND s.region = {{regionFilter}}"
        params["regionFilter"] = region_filter

    rows = await raw_query(
        f"""WITH visit_stats AS (
      SELECT
        {inner_group_by},
        we.visit_id,
        COUNT(*) AS pages,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration
      FROM website_event we
      JOIN session s ON s.session_id = we.session_id
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        AND s.country IS NOT NULL
        {extra_filter}
        {filter_where}
      GROUP BY {inner_group_by}, we.visit_id
    )
    SELECT
      {outer_select_geo}
      COUNT(DISTINCT visit_id)::bigint AS visitors,
      SUM(pages)::bigint AS pageviews,
      COUNT(visit_id)::bigint AS visits,
      CASE WHEN COUNT(*) = 0 THEN 0
        ELSE (SUM(CASE WHEN pages = 1 THEN 1 ELSE 0 END)::float / COUNT(*) * 100)
      END AS bounce_rate,
      COALESCE(AVG(duration), 0) AS avg_duration
    FROM visit_stats
    GROUP BY {outer_group_by}
    ORDER BY visitors DESC
    LIMIT {limit}""",
        params,
    )

    return [
        {
            "country": row["country"],
            "region": row["region"],
            "city": row["city"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "visits": int(row["visits"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
            "avgDuration": row["avg_duration"] or 0,
        }
        for row in rows
    ]
