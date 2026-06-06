"""Page-level analytics queries — aggregate pageview metrics per URL.

Privacy-first: only pageview counts per URL. No visitors, sessions, bounce rates,
time-on-page, entry/exit, or navigation tracking (those require persistent identifiers).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, GRANULARITIES, safe_identifier


def get_page_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    page_mode: str = "path",
) -> list[dict[str, Any]]:
    """Compute aggregate per-page pageview counts with pagination.

    Returns each tracked URL with its view count and most recent page title.
    Visitor/session/bounce/time metrics are not available because they require
    persistent identifiers.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of page rows per page of results (default 50).
        offset: Row offset for pagination (default 0).
        filters: Optional list of column filters to narrow the dataset.
        page_mode: URL normalization mode -- ``"path"`` or ``"slug"``.

    Returns:
        List of dicts with ``urlPath``, ``pageTitle``, ``views``, sorted by
        views descending.
    """
    filters = filters or []

    if page_mode == "slug":
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        slug_coalesce = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        slug_coalesce = "we.url_path"

    rows = raw_query(
        f"""SELECT
      {slug_coalesce} AS url_path,
      MAX(we.page_title) AS page_title,
      COUNT(*)::bigint AS views
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
    GROUP BY url_path
    ORDER BY views DESC
    LIMIT {limit} OFFSET {offset}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    return [
        {
            "urlPath": row["url_path"],
            "pageTitle": row["page_title"],
            "views": int(row["views"] or 0),
        }
        for row in rows
    ]


def get_page_time_series(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Generate a time series of pageviews for a specific page."""
    filters = filters or []
    gran = granularity if granularity in ("minute", "hour", "day", "week", "month") else "day"

    rows = raw_query(
        f"""SELECT
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS views
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.url_path = {{urlPath}}
    GROUP BY 1
    ORDER BY 1 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "views": int(row["views"] or 0),
        }
        for row in rows
    ]
