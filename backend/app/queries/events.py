from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query
from ..filters import Filter, build_filter_sql


async def get_event_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
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
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      MAX(we.created_at) AS last_triggered
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
            "lastTriggered": row["last_triggered"].isoformat()
            if isinstance(row["last_triggered"], datetime)
            else (str(row["last_triggered"]) if row["last_triggered"] else None),
        }
        for row in rows
    ]


async def get_event_time_series(
    website_id: str,
    event_name: str,
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
      COUNT(*)::bigint AS count
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name = {{eventName}}
      {filter_where}
    GROUP BY 1
    ORDER BY 1 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventName": event_name,
            **filter_params,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "count": int(row["count"] or 0),
        }
        for row in rows
    ]


async def get_event_properties(
    website_id: str,
    event_name: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""SELECT
      ed.data_key,
      COALESCE(ed.string_value, ed.number_value::text) AS value,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM event_data ed
    JOIN website_event we ON ed.website_event_id = we.event_id
    WHERE ed.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_name = {{eventName}}
    GROUP BY 1, 2
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventName": event_name,
        },
    )

    return [
        {
            "dataKey": row["data_key"],
            "value": row["value"],
            "count": int(row["count"] or 0),
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]
