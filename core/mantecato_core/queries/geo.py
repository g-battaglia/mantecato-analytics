"""Geographic breakdown queries — country / region / city with bounce rate and avg duration.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
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
    level: str = "country",
    country_filter: str | None = None,
    region_filter: str | None = None,
    url_path: str | None = None,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Compute visitor, pageview, bounce rate, and duration metrics by geography.

    Supports three drill-down levels:

    - ``"country"`` -- top-level breakdown by ISO country code.
    - ``"region"`` -- breakdown by region within a country (requires
      ``country_filter``).
    - ``"city"`` -- breakdown by city within a region (requires both
      ``country_filter`` and ``region_filter``).

    The ``country_filter`` and ``region_filter`` parameters enable
    hierarchical drill-down: clicking a country shows its regions,
    clicking a region shows its cities.

    An optional ``url_path`` parameter further narrows the analysis
    to visits that included a specific page.

    The query uses a two-phase CTE (``visit_stats``): the inner CTE
    computes per-visit page count and duration grouped by the
    appropriate geo columns, and the outer query aggregates across
    visits to produce bounce rate and average duration.

    The GROUP BY and SELECT clauses are dynamically constructed based
    on ``level`` to include only the relevant geo columns (e.g. at
    country level, region and city are returned as NULL).

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        level: Geographic granularity -- ``"country"``, ``"region"``,
            or ``"city"`` (default ``"country"``).
        country_filter: ISO country code to restrict results to a
            single country (required for region/city level).
        region_filter: Region name to restrict results to a single
            region (used only at city level).
        url_path: Optional page URL path to narrow the analysis.
        limit: Maximum number of rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``country`` (str): ISO country code.
        - ``region`` (str | None): Region name (NULL at country level).
        - ``city`` (str | None): City name (NULL at country/region level).
        - ``visitors`` (int): Unique visitor (visit_id) count.
        - ``pageviews`` (int): Total pageview count.
        - ``visits`` (int): Total visit count.
        - ``bounceRate`` (float): Percentage of single-page visits.
        - ``avgDuration`` (float): Average visit duration in seconds.
        Sorted by visitors descending.
    """
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

    # Optional page-level filter to narrow geo breakdown to a specific page.
    page_filter = ""
    if url_path:
        page_filter = " AND we.url_path = {{urlPath}}"
        params["urlPath"] = url_path

    # Dynamically construct GROUP BY and SELECT clauses based on the
    # requested geographic level.  At higher levels (country), lower
    # columns (region, city) are returned as NULL for uniform output shape.
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

    # Hierarchical drill-down filters: narrow to a specific country
    # when viewing regions, or to country + region when viewing cities.
    extra_filter = ""
    if country_filter and level in ("region", "city"):
        extra_filter += " AND s.country = {{countryFilter}}"
        params["countryFilter"] = country_filter
    if region_filter and level == "city":
        extra_filter += " AND s.region = {{regionFilter}}"
        params["regionFilter"] = region_filter

    rows = raw_query(
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
        {page_filter}
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
