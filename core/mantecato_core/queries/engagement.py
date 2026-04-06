"""
Engagement queries — duration distribution, percentiles, duration by page,
bounce rate by page, bounce rate by source.
Ported verbatim from src/queries/engagement.ts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query
from mantecato_core.filters import Filter, build_filter_sql


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


BUCKET_RANGES: dict[str, tuple[float, float | None]] = {
    "0s (bounce)": (0, 0),
    "1-10s": (0.1, 10),
    "10-30s": (10, 30),
    "30s-1m": (30, 60),
    "1-3m": (60, 180),
    "3-10m": (180, 600),
    "10-30m": (600, 1800),
    "30m+": (1800, None),
}


async def get_sessions_for_bucket(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    bucket: str,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    entry_page: str | None = None,
) -> dict[str, Any]:
    filters = filters or []
    range_spec = BUCKET_RANGES.get(bucket)
    if range_spec is None:
        return {
            "sessions": [],
            "total": 0,
            "countries": [],
            "cities": [],
            "pages": [],
            "entryPages": [],
            "journeys": [],
            "sources": [],
            "devices": [],
        }

    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    min_secs, max_secs = range_spec
    duration_filter = f"AND bv.duration_secs >= {min_secs}"
    if max_secs is not None:
        if min_secs == 0 and max_secs == 0:
            duration_filter += " AND bv.duration_secs = 0"
        else:
            duration_filter += f" AND bv.duration_secs < {max_secs}"

    entry_page_filter = ""
    params = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
        **filter_params,
    }
    if entry_page:
        entry_page_filter = " AND ve.entry_page = {{entryPage}}"
        params["entryPage"] = entry_page

    base_cte = f"""WITH filtered_events AS (
      SELECT
        we.visit_id,
        we.session_id,
        we.url_path,
        we.referrer_domain,
        we.created_at
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
        {filter_where}
    ),
    visit_entries AS (
      SELECT DISTINCT ON (fe.visit_id)
        fe.visit_id,
        COALESCE(fe.url_path, '(unknown)') AS entry_page,
        COALESCE(NULLIF(fe.referrer_domain, ''), '(direct)') AS entry_referrer
      FROM filtered_events fe
      ORDER BY fe.visit_id, fe.created_at ASC
    ),
    bucket_visits AS (
      SELECT
        fe.visit_id,
        fe.session_id,
        COUNT(*)::bigint AS pages_viewed,
        EXTRACT(EPOCH FROM (MAX(fe.created_at) - MIN(fe.created_at))) AS duration_secs,
        MIN(fe.created_at) AS started_at
      FROM filtered_events fe
      GROUP BY fe.visit_id, fe.session_id
    ),
    bucket_scope AS (
      SELECT
        bv.visit_id,
        bv.session_id,
        bv.pages_viewed,
        bv.duration_secs,
        bv.started_at,
        ve.entry_page,
        ve.entry_referrer
      FROM bucket_visits bv
      JOIN visit_entries ve ON ve.visit_id = bv.visit_id
      WHERE 1=1
        {duration_filter}
        {entry_page_filter}
    )"""

    count_task = raw_query(
        f"""{base_cte}
    SELECT COUNT(*)::bigint AS total
    FROM bucket_scope bs""",
        params,
    )

    sessions_task = raw_query(
        f"""{base_cte}
    SELECT
      bs.visit_id,
      bs.session_id,
      COALESCE(s.country, '(not set)') AS country,
      COALESCE(s.city, '(not set)') AS city,
      COALESCE(s.browser, 'Unknown') AS browser,
      COALESCE(s.os, 'Unknown') AS os,
      COALESCE(s.device, 'Unknown') AS device,
      bs.entry_page AS landing_page,
      bs.pages_viewed,
      bs.duration_secs,
      bs.started_at
    FROM bucket_scope bs
    JOIN session s ON s.session_id = bs.session_id
    ORDER BY bs.started_at DESC
    LIMIT {limit} OFFSET {offset}""",
        params,
    )

    countries_task = raw_query(
        f"""{base_cte}
    SELECT
      COALESCE(s.country, '(not set)') AS country,
      COUNT(*)::bigint AS visits
    FROM bucket_scope bs
    JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1
    ORDER BY visits DESC, country ASC
    LIMIT 12""",
        params,
    )

    cities_task = raw_query(
        f"""{base_cte}
    SELECT
      COALESCE(s.country, '(not set)') AS country,
      COALESCE(s.city, '(not set)') AS city,
      COUNT(*)::bigint AS visits
    FROM bucket_scope bs
    JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1, 2
    ORDER BY visits DESC, country ASC, city ASC
    LIMIT 12""",
        params,
    )

    pages_task = raw_query(
        f"""{base_cte}
    SELECT
      fe.url_path,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT fe.visit_id)::bigint AS visits
    FROM filtered_events fe
    JOIN bucket_scope bs ON bs.visit_id = fe.visit_id
    GROUP BY fe.url_path
    ORDER BY views DESC, visits DESC, fe.url_path ASC
    LIMIT 20""",
        params,
    )

    entry_pages_task = raw_query(
        f"""{base_cte}
    SELECT
      bs.entry_page,
      COUNT(*)::bigint AS visits
    FROM bucket_scope bs
    GROUP BY 1
    ORDER BY visits DESC, entry_page ASC
    LIMIT 12""",
        params,
    )

    journeys_task = raw_query(
        f"""{base_cte},
    visit_pages AS (
      SELECT
        fe.visit_id,
        fe.url_path,
        ROW_NUMBER() OVER (PARTITION BY fe.visit_id ORDER BY fe.created_at) AS rn
      FROM filtered_events fe
      JOIN bucket_scope bs ON bs.visit_id = fe.visit_id
    ),
    visit_journeys AS (
      SELECT
        visit_id,
        array_agg(url_path ORDER BY rn) AS journey
      FROM visit_pages
      WHERE rn <= 4
      GROUP BY visit_id
      HAVING COUNT(*) >= 2
    )
    SELECT
      journey,
      COUNT(*)::bigint AS count
    FROM visit_journeys
    GROUP BY journey
    ORDER BY count DESC
    LIMIT 15""",
        params,
    )

    sources_task = raw_query(
        f"""{base_cte}
    SELECT
      bs.entry_referrer AS referrer_domain,
      COUNT(*)::bigint AS visits
    FROM bucket_scope bs
    GROUP BY 1
    ORDER BY visits DESC, referrer_domain ASC
    LIMIT 12""",
        params,
    )

    devices_task = raw_query(
        f"""{base_cte}
    SELECT
      COALESCE(s.browser, 'Unknown') AS browser,
      COALESCE(s.device, 'Unknown') AS device,
      COALESCE(s.os, 'Unknown') AS os,
      COUNT(*)::bigint AS visits
    FROM bucket_scope bs
    JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1, 2, 3
    ORDER BY visits DESC, browser ASC, device ASC, os ASC
    LIMIT 12""",
        params,
    )

    (
        count_row,
        session_rows,
        country_rows,
        city_rows,
        page_rows,
        entry_page_rows,
        journey_rows,
        source_rows,
        device_rows,
    ) = await asyncio.gather(
        count_task,
        sessions_task,
        countries_task,
        cities_task,
        pages_task,
        entry_pages_task,
        journeys_task,
        sources_task,
        devices_task,
    )

    total = int(count_row[0]["total"] or 0) if count_row else 0

    sessions = [
        {
            "visitId": row["visit_id"],
            "sessionId": row["session_id"],
            "country": row["country"],
            "city": row["city"],
            "browser": row["browser"],
            "os": row["os"],
            "device": row["device"],
            "landingPage": row["landing_page"],
            "pagesViewed": int(row["pages_viewed"] or 0),
            "durationSecs": round(float(row["duration_secs"] or 0), 1),
            "startedAt": row["started_at"].isoformat()
            if hasattr(row["started_at"], "isoformat")
            else str(row["started_at"]),
        }
        for row in session_rows
    ]

    countries = [
        {
            "country": row["country"],
            "visits": int(row["visits"] or 0),
        }
        for row in country_rows
    ]
    cities = [
        {
            "country": row["country"],
            "city": row["city"],
            "visits": int(row["visits"] or 0),
        }
        for row in city_rows
    ]
    pages = [
        {
            "urlPath": row["url_path"],
            "views": int(row["views"] or 0),
            "visits": int(row["visits"] or 0),
        }
        for row in page_rows
    ]
    entry_pages = [
        {
            "urlPath": row["entry_page"],
            "visits": int(row["visits"] or 0),
            "percentage": (int(row["visits"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in entry_page_rows
    ]
    journeys = [
        {
            "path": row["journey"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in journey_rows
    ]
    sources = [
        {
            "referrerDomain": row["referrer_domain"],
            "visits": int(row["visits"] or 0),
        }
        for row in source_rows
    ]
    devices = [
        {
            "browser": row["browser"],
            "device": row["device"],
            "os": row["os"],
            "visits": int(row["visits"] or 0),
        }
        for row in device_rows
    ]

    return {
        "sessions": sessions,
        "total": total,
        "countries": countries,
        "cities": cities,
        "pages": pages,
        "entryPages": entry_pages,
        "journeys": journeys,
        "sources": sources,
        "devices": devices,
    }
