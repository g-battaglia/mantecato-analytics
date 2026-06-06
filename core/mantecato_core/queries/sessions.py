"""Session queries — session list and per-session activity replay.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, build_filter_sql


def get_session_list(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    visited_page: str | None = None,
    triggered_event: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve a paginated list of sessions with device and geo metadata.

    Returns one row per session, enriched with data from the ``session``
    table (country, city, browser, OS, device type).  The list is
    ordered by most recent session first and supports pagination via
    ``limit`` / ``offset``.

    Optional behavioral filters narrow the list to sessions that:

    - **visited_page** -- viewed a specific URL path (pageview filter).
    - **triggered_event** -- fired a specific custom event.

    These behavioral filters use correlated ``IN (SELECT ...)`` subqueries
    appended to the WHERE clause.  While a JOIN could achieve the same
    result, subqueries are used here to keep the main GROUP BY simple
    and avoid multiplying rows when a session matches multiple events.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum sessions to return (default 50).
        offset: Row offset for pagination (default 0).
        filters: Optional list of column filters (device, geo, etc.).
        visited_page: If set, only return sessions that viewed this
            exact URL path.
        triggered_event: If set, only return sessions that fired this
            exact custom event name.

    Returns:
        List of dicts, each containing:
        - ``sessionId`` (str): UUID of the session.
        - ``country`` (str | None): ISO country code.
        - ``city`` (str | None): City name.
        - ``browser`` (str | None): Browser name.
        - ``os`` (str | None): Operating system name.
        - ``device`` (str | None): Device type (desktop/mobile/tablet).
        - ``pagesViewed`` (int): Number of pageviews in this session.
        - ``duration`` (float): Session duration in seconds.
        - ``startedAt`` (str): ISO 8601 timestamp of first pageview.
        Sorted by startedAt descending (most recent first).
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

    # Build optional behavioral filter subqueries.  Each uses a correlated
    # IN (SELECT ...) rather than a JOIN to avoid row multiplication.
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

    rows = raw_query(
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


def get_session_activity(
    session_id: str,
    website_id: str,
) -> list[dict[str, Any]]:
    """Retrieve the full chronological activity log for a single session.

    Returns every event (both pageviews and custom events) in the
    session, ordered by timestamp.  Each row includes any associated
    event properties from the ``event_data`` table, aggregated into
    a JSON array via ``json_agg(json_build_object(...))``.

    The ``LEFT JOIN`` to ``event_data`` ensures pageviews (which
    typically have no properties) still appear in the results.  The
    ``FILTER (WHERE ed.data_key IS NOT NULL)`` clause prevents NULL
    entries in the aggregated JSON when no properties exist.

    The GROUP BY includes ``we.event_id`` to ensure each event row is
    unique, even if the same URL is visited multiple times in the session.

    The ``website_id`` parameter is included in the WHERE clause as a
    security guard to prevent cross-website session enumeration.

    Args:
        session_id: UUID of the session to inspect.
        website_id: UUID of the tracked website (ownership check).

    Returns:
        List of dicts ordered chronologically, each containing:
        - ``createdAt`` (str): ISO 8601 timestamp.
        - ``urlPath`` (str | None): Page URL (for pageviews).
        - ``pageTitle`` (str | None): Page title (for pageviews).
        - ``eventType`` (int): 1 = pageview, 2 = custom event.
        - ``eventName`` (str | None): Custom event name (if type 2).
        - ``referrerDomain`` (str | None): Referrer for this event.
        - ``visitId`` (str): UUID of the visit within the session.
        - ``eventData`` (list[dict] | None): Key-value properties, or
          None if no properties were attached.
    """
    rows = raw_query(
        """SELECT
      we.created_at,
      we.url_path,
      we.page_title,
      we.event_type,
      we.event_name,
      we.referrer_domain,
      we.visit_id,
      json_agg(
        json_build_object(
          'key', ed.data_key,
          'value', COALESCE(ed.string_value, ed.number_value::text)
        )
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
