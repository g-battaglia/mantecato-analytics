from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query
from mantecato_core.filters import Filter, build_filter_sql


async def get_website_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
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
        f"""SELECT
      COALESCE(SUM(t.c), 0)::bigint AS pageviews,
      COUNT(DISTINCT t.session_id)::bigint AS visitors,
      COUNT(DISTINCT t.visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN t.c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (t.max_time - t.min_time)))), 0)::bigint AS totaltime
    FROM (
      SELECT
        we.session_id, we.visit_id,
        COUNT(*) AS c,
        MIN(we.created_at) AS min_time,
        MAX(we.created_at) AS max_time
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.session_id, we.visit_id
    ) AS t""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    row = rows[0] if rows else {}
    return {
        "pageviews": int(row.get("pageviews") or 0),
        "visitors": int(row.get("visitors") or 0),
        "visits": int(row.get("visits") or 0),
        "bounces": int(row.get("bounces") or 0),
        "totaltime": int(row.get("totaltime") or 0),
    }


async def get_pageview_time_series(
    website_id: str,
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

    gran_interval = {
        "minute": "1 minute",
        "hour": "1 hour",
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
    }.get(gran, "1 day")

    rows = await raw_query(
        f"""WITH buckets AS (
      SELECT generate_series(
        date_trunc('{gran}', {{startDate::timestamptz}}),
        date_trunc('{gran}', {{endDate::timestamptz}}),
        '{gran_interval}'::interval
      ) AS time
    ),
    data AS (
      SELECT
        date_trunc('{gran}', we.created_at) AS time,
        COUNT(*)::bigint AS pageviews,
        COUNT(DISTINCT we.session_id)::bigint AS visitors
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY 1
    )
    SELECT
      b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews,
      COALESCE(d.visitors, 0)::bigint AS visitors
    FROM buckets b
    LEFT JOIN data d ON d.time = b.time
    ORDER BY b.time ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "pageviews": int(row["pageviews"] or 0),
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]


async def get_top_pages(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
    page_mode: str = "path",
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    if page_mode == "slug":
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        url_select = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        url_select = "we.url_path"

    rows = await raw_query(
        f"""SELECT
      {url_select} AS url_path,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      {filter_where}
    GROUP BY url_path
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
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]


async def get_top_sections(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    depth: int = 2,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Group pages by the first `depth` path segments and aggregate stats."""
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]
    session_join = (
        "JOIN session s ON s.session_id = we.session_id"
        if result["needs_session_join"]
        else ""
    )

    # depth+1 because string_to_array splits '/a/b' into ['','a','b']
    slice_end = depth + 1

    # Clean URL: strip query params, hash fragments, trailing slashes
    clean_url = "REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(we.url_path, '?', 1), '#', 1), '/+$', '')"

    rows = await raw_query(
        f"""SELECT
      section,
      SUM(views)::bigint AS views,
      SUM(visitors)::bigint AS visitors,
      COUNT(*)::bigint AS pages
    FROM (
      SELECT
        COALESCE(
          NULLIF(array_to_string((string_to_array({clean_url}, '/'))[1:{slice_end}], '/'), ''),
          '/'
        ) AS section,
        COUNT(*)::bigint AS views,
        COUNT(DISTINCT we.session_id)::bigint AS visitors
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY {clean_url}
    ) sub
    GROUP BY section
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
            "section": row["section"],
            "views": int(row["views"] or 0),
            "visitors": int(row["visitors"] or 0),
            "pages": int(row["pages"] or 0),
        }
        for row in rows
    ]


async def get_top_referrers(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
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
        f"""SELECT
      we.referrer_domain,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.referrer_domain IS NOT NULL
      AND we.referrer_domain != ''
      {filter_where}
    GROUP BY we.referrer_domain
    ORDER BY visitors DESC
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
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]


async def get_top_events(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
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
        f"""SELECT
      we.event_name,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name IS NOT NULL
      {filter_where}
    GROUP BY we.event_name
    ORDER BY count DESC
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
            "eventName": row["event_name"],
            "count": int(row["count"] or 0),
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]


async def get_top_events_with_properties(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    properties_limit: int = 3,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Get top events with their top property values inlined.

    1. Fetches the top N events (same as get_top_events).
    2. For each event, fetches the top `properties_limit` property key:value pairs
       from the event_data table in a single batched query.
    3. Returns events with a `properties` list attached.
    """
    events = await get_top_events(
        website_id, start_date, end_date, limit, filters
    )
    if not events:
        return events

    event_names = [e["eventName"] for e in events]

    # Single query to get top properties for all top events at once.
    # We use ROW_NUMBER to pick the top N per event name.
    rows = await raw_query(
        f"""SELECT event_name, data_key, value, count
    FROM (
      SELECT
        we.event_name,
        ed.data_key,
        COALESCE(ed.string_value, ed.number_value::text) AS value,
        COUNT(*)::bigint AS count,
        ROW_NUMBER() OVER (
          PARTITION BY we.event_name
          ORDER BY COUNT(*) DESC
        ) AS rn
      FROM event_data ed
      JOIN website_event we ON ed.website_event_id = we.event_id
      WHERE ed.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_name = ANY({{eventNames::text[]}})
      GROUP BY we.event_name, ed.data_key, value
    ) sub
    WHERE rn <= {properties_limit}
    ORDER BY event_name, count DESC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventNames": event_names,
        },
    )

    # Group properties by event name
    props_by_event: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        name = row["event_name"]
        if name not in props_by_event:
            props_by_event[name] = []
        props_by_event[name].append(
            {
                "key": row["data_key"],
                "value": row["value"],
                "count": int(row["count"] or 0),
            }
        )

    for event in events:
        event["properties"] = props_by_event.get(event["eventName"], [])

    return events


async def get_device_breakdown(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    field: str,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    valid_fields = ["browser", "os", "device"]
    if field not in valid_fields:
        return []
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    rows = await raw_query(
        f"""SELECT
      s.{field} AS value,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.{field} IS NOT NULL
      {filter_where}
    GROUP BY s.{field}
    ORDER BY visitors DESC
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
            "value": row["value"],
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]


async def get_country_breakdown(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    rows = await raw_query(
        f"""SELECT
      s.country,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.country IS NOT NULL
      {filter_where}
    GROUP BY s.country
    ORDER BY visitors DESC
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
            "country": row["country"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]
