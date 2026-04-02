"""
Engagement queries — duration distribution, percentiles, duration by page,
bounce rate by page, bounce rate by source.
Ported verbatim from src/queries/engagement.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query
from ..filters import Filter, build_filter_sql


async def get_duration_distribution(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Visit duration histogram buckets."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id
    ),
    bucketed AS (
      SELECT
        CASE
          WHEN duration_secs = 0 THEN '0s (bounce)'
          WHEN duration_secs < 10 THEN '1-10s'
          WHEN duration_secs < 30 THEN '10-30s'
          WHEN duration_secs < 60 THEN '30s-1m'
          WHEN duration_secs < 180 THEN '1-3m'
          WHEN duration_secs < 600 THEN '3-10m'
          WHEN duration_secs < 1800 THEN '10-30m'
          ELSE '30m+'
        END AS bucket,
        CASE
          WHEN duration_secs = 0 THEN 0
          WHEN duration_secs < 10 THEN 1
          WHEN duration_secs < 30 THEN 2
          WHEN duration_secs < 60 THEN 3
          WHEN duration_secs < 180 THEN 4
          WHEN duration_secs < 600 THEN 5
          WHEN duration_secs < 1800 THEN 6
          ELSE 7
        END AS bucket_order
      FROM visit_durations
    )
    SELECT bucket, bucket_order, COUNT(*)::bigint AS visits
    FROM bucketed
    GROUP BY bucket, bucket_order
    ORDER BY bucket_order""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    total = sum(int(r["visits"] or 0) for r in rows)

    return [
        {
            "bucket": row["bucket"],
            "bucketOrder": int(row["bucket_order"] or 0),
            "visits": int(row["visits"] or 0),
            "percentage": (int(row["visits"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


async def get_duration_percentiles(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Duration percentiles (p50, p75, p90, p95, p99, avg, min, max)."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id
      HAVING COUNT(*) > 1
    )
    SELECT
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_secs) AS p50,
      PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_secs) AS p75,
      PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_secs) AS p90,
      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_secs) AS p95,
      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_secs) AS p99,
      AVG(duration_secs) AS avg,
      MIN(duration_secs) AS min_dur,
      MAX(duration_secs) AS max_dur,
      COUNT(*)::bigint AS total_visits
    FROM visit_durations""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    row = rows[0] if rows else {}
    p50 = float(row.get("p50") or 0)

    return {
        "p50": p50,
        "p75": float(row.get("p75") or 0),
        "p90": float(row.get("p90") or 0),
        "p95": float(row.get("p95") or 0),
        "p99": float(row.get("p99") or 0),
        "avg": float(row.get("avg") or 0),
        "median": p50,
        "min": float(row.get("min_dur") or 0),
        "max": float(row.get("max_dur") or 0),
        "totalVisits": int(row.get("total_visits") or 0),
    }


async def get_duration_by_page(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Avg, median, p90 duration by page."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH page_sequence AS (
      SELECT
        we.url_path,
        we.visit_id,
        we.created_at,
        LEAD(we.created_at) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) AS next_page_at
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS views,
      AVG(EXTRACT(EPOCH FROM (next_page_at - created_at)))
        FILTER (WHERE next_page_at IS NOT NULL) AS avg_duration,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS median_duration,
      PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS p90_duration
    FROM page_sequence
    GROUP BY url_path
    HAVING COUNT(*) FILTER (WHERE next_page_at IS NOT NULL) > 0
    ORDER BY views DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "urlPath": row["url_path"],
            "views": int(row["views"] or 0),
            "avgDuration": float(row["avg_duration"] or 0),
            "medianDuration": float(row["median_duration"] or 0),
            "p90Duration": float(row["p90_duration"] or 0),
        }
        for row in rows
    ]


async def get_bounce_rate_by_page(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Bounce rate breakdown by entry page."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH entry_pages AS (
      SELECT
        we.visit_id,
        we.url_path,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM entry_pages
    WHERE rn = 1
    GROUP BY url_path
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "urlPath": row["url_path"],
            "totalVisits": int(row["total_visits"] or 0),
            "bounces": int(row["bounces"] or 0),
            "bounceRate": float(row["bounce_rate"] or 0),
        }
        for row in rows
    ]


async def get_bounce_rate_by_source(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Bounce rate breakdown by referrer source."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""WITH visit_info AS (
      SELECT
        we.visit_id,
        we.referrer_domain,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
    )
    SELECT
      COALESCE(referrer_domain, '(direct)') AS referrer_domain,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM visit_info
    WHERE rn = 1
    GROUP BY referrer_domain
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "referrerDomain": row["referrer_domain"],
            "totalVisits": int(row["total_visits"] or 0),
            "bounces": int(row["bounces"] or 0),
            "bounceRate": float(row["bounce_rate"] or 0),
        }
        for row in rows
    ]
