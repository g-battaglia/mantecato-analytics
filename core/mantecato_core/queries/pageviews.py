from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query
from mantecato_core.filters import Filter, build_filter_sql


async def get_page_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    page_mode: str = "path",
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join_cte = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    if page_mode == "slug":
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        slug_coalesce = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        url_expr = "we.url_path"
        slug_coalesce = url_expr

    rows = await raw_query(
        f"""WITH filtered_events AS (
      SELECT {slug_coalesce} AS url_path, we.page_title, we.visit_id, we.session_id, we.created_at
      FROM website_event we
      {session_join_cte}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    ),
    page_sequence AS (
      SELECT
        url_path,
        page_title,
        visit_id,
        session_id,
        created_at,
        LEAD(created_at) OVER (PARTITION BY visit_id ORDER BY created_at) AS next_page_at,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at ASC) AS rn_entry,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at DESC) AS rn_exit
      FROM filtered_events
    ),
    visit_bounces AS (
      SELECT visit_id, COUNT(*) AS page_count
      FROM filtered_events
      GROUP BY visit_id
    )
    SELECT
      ps.url_path,
      MAX(ps.page_title) AS page_title,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT ps.session_id)::bigint AS visitors,
      AVG(EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at)))
        FILTER (WHERE ps.next_page_at IS NOT NULL) AS avg_time_on_page,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at))
      ) FILTER (WHERE ps.next_page_at IS NOT NULL) AS median_time_on_page,
      COUNT(*) FILTER (WHERE ps.rn_entry = 1)::bigint AS entries,
      COUNT(*) FILTER (WHERE ps.rn_exit = 1)::bigint AS exits,
      CASE
        WHEN COUNT(*) FILTER (WHERE ps.rn_entry = 1) = 0 THEN 0
        ELSE (
          COUNT(*) FILTER (WHERE ps.rn_entry = 1 AND vb.page_count = 1)::float /
          NULLIF(COUNT(*) FILTER (WHERE ps.rn_entry = 1), 0) * 100
        )
      END AS bounce_rate
    FROM page_sequence ps
    LEFT JOIN visit_bounces vb ON ps.visit_id = vb.visit_id
    GROUP BY ps.url_path
    ORDER BY views DESC
    LIMIT {limit} OFFSET {offset}""",
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
            "pageTitle": row["page_title"],
            "views": int(row["views"] or 0),
            "visitors": int(row["visitors"] or 0),
            "avgTimeOnPage": row["avg_time_on_page"],
            "medianTimeOnPage": row["median_time_on_page"],
            "entries": int(row["entries"] or 0),
            "exits": int(row["exits"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
        }
        for row in rows
    ]


async def get_page_referrers(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""SELECT
      COALESCE(NULLIF(we.referrer_domain, ''), '(direct)') AS referrer_domain,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS views
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.url_path = {{urlPath}}
    GROUP BY 1
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    return [
        {
            "referrerDomain": row["referrer_domain"],
            "visitors": int(row["visitors"] or 0),
            "views": int(row["views"] or 0),
        }
        for row in rows
    ]


async def get_next_pages(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""WITH page_nav AS (
      SELECT
        we.url_path,
        we.visit_id,
        we.created_at,
        LEAD(we.url_path) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) AS next_url
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
    )
    SELECT
      next_url,
      COUNT(*)::bigint AS count
    FROM page_nav
    WHERE url_path = {{urlPath}}
      AND next_url IS NOT NULL
      AND next_url != {{urlPath}}
    GROUP BY next_url
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    total = sum(int(r["count"] or 0) for r in rows)
    return [
        {
            "urlPath": row["next_url"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


async def get_time_on_page_distribution(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        """WITH page_durations AS (
      SELECT
        EXTRACT(EPOCH FROM (
          LEAD(we.created_at) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) - we.created_at
        )) AS duration_sec
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.url_path = {{urlPath}}
    )
    SELECT
      CASE
        WHEN duration_sec IS NULL THEN 'Exit'
        WHEN duration_sec < 5 THEN '0-5s'
        WHEN duration_sec < 15 THEN '5-15s'
        WHEN duration_sec < 30 THEN '15-30s'
        WHEN duration_sec < 60 THEN '30-60s'
        WHEN duration_sec < 120 THEN '1-2m'
        WHEN duration_sec < 300 THEN '2-5m'
        ELSE '5m+'
      END AS bucket,
      COUNT(*)::bigint AS count
    FROM page_durations
    GROUP BY 1
    ORDER BY MIN(CASE
        WHEN duration_sec IS NULL THEN 8
        WHEN duration_sec < 5 THEN 1
        WHEN duration_sec < 15 THEN 2
        WHEN duration_sec < 30 THEN 3
        WHEN duration_sec < 60 THEN 4
        WHEN duration_sec < 120 THEN 5
        WHEN duration_sec < 300 THEN 6
        ELSE 7
      END)""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    return [
        {
            "bucket": row["bucket"],
            "count": int(row["count"] or 0),
        }
        for row in rows
    ]


async def get_page_time_series(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    valid_granularities = ["minute", "hour", "day", "week", "month"]
    gran = granularity if granularity in valid_granularities else "day"
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    rows = await raw_query(
        f"""SELECT
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.url_path = {{urlPath}}
      {filter_where}
    GROUP BY 1
    ORDER BY 1 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
            **filter_params,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "views": int(row["views"] or 0),
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]
