from __future__ import annotations

from datetime import datetime
from typing import Any

from mantecato_core.database import raw_query
from mantecato_core.filters import Filter, build_filter_sql


async def get_session_list(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    visited_page: str | None = None,
    triggered_event: str | None = None,
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

    extra_subqueries: list[str] = []

    if visited_page:
        extra_subqueries.append(
            """AND we.session_id IN (
        SELECT vp.session_id FROM website_event vp
        WHERE vp.website_id = {{websiteId::uuid}}
          AND vp.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
          AND vp.event_type = 1
          AND vp.url_path = {{visitedPage}}
      )"""
        )
        params["visitedPage"] = visited_page

    if triggered_event:
        extra_subqueries.append(
            """AND we.session_id IN (
        SELECT te.session_id FROM website_event te
        WHERE te.website_id = {{websiteId::uuid}}
          AND te.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
          AND te.event_type = 2
          AND te.event_name = {{triggeredEvent}}
      )"""
        )
        params["triggeredEvent"] = triggered_event

    extra_sql = "\n      ".join(extra_subqueries)

    rows = await raw_query(
        f"""SELECT
      we.session_id,
      s.country,
      s.city,
      s.browser,
      s.os,
      s.device,
      COUNT(*)::bigint AS pages_viewed,
      EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration,
      MIN(we.created_at) AS started_at
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      {filter_where}
      {extra_sql}
    GROUP BY we.session_id, s.country, s.city, s.browser, s.os, s.device
    ORDER BY started_at DESC
    LIMIT {limit} OFFSET {offset}""",
        params,
    )

    return [
        {
            "sessionId": row["session_id"],
            "country": row["country"],
            "city": row["city"],
            "browser": row["browser"],
            "os": row["os"],
            "device": row["device"],
            "pagesViewed": int(row["pages_viewed"] or 0),
            "duration": row["duration"] or 0,
            "startedAt": row["started_at"].isoformat()
            if isinstance(row["started_at"], datetime)
            else str(row["started_at"]),
        }
        for row in rows
    ]


async def get_session_activity(
    session_id: str,
    website_id: str,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        """SELECT
      we.created_at,
      we.url_path,
      we.page_title,
      we.event_type,
      we.event_name,
      we.referrer_domain,
      we.visit_id,
      json_agg(
        json_build_object('key', ed.data_key, 'value', COALESCE(ed.string_value, ed.number_value::text))
      ) FILTER (WHERE ed.data_key IS NOT NULL) AS event_data
    FROM website_event we
    LEFT JOIN event_data ed ON we.event_id = ed.website_event_id
    WHERE we.session_id = {{sessionId::uuid}}
      AND we.website_id = {{websiteId::uuid}}
    GROUP BY we.event_id, we.created_at, we.url_path, we.page_title,
             we.event_type, we.event_name, we.referrer_domain, we.visit_id
    ORDER BY we.created_at ASC""",
        {"sessionId": session_id, "websiteId": website_id},
    )

    return [
        {
            "createdAt": row["created_at"].isoformat()
            if isinstance(row["created_at"], datetime)
            else str(row["created_at"]),
            "urlPath": row["url_path"],
            "pageTitle": row["page_title"],
            "eventType": row["event_type"],
            "eventName": row["event_name"],
            "referrerDomain": row["referrer_domain"],
            "visitId": row["visit_id"],
            "eventData": row["event_data"],
        }
        for row in rows
    ]
