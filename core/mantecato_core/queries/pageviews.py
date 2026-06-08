"""Page-level analytics queries — aggregate pageview metrics per URL.

Privacy-first: only pageview counts per URL. No visitors, sessions, bounce rates,
time-on-page, entry/exit, or navigation tracking (those require persistent identifiers).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, GRANULARITIES, prepare_filters, safe_identifier
from core.mantecato_core.queries.orm_fallbacks import (
    pageview_queryset,
    pageview_time_series_rows,
    should_use_orm_fallback,
)


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
    if should_use_orm_fallback():
        from django.db.models import Count, Max

        rows = (
            pageview_queryset(website_id, start_date, end_date, filters)
            .values("url_path")
            .annotate(page_title=Max("page_title"), views=Count("event_id"))
            .order_by("-views", "url_path")[offset : offset + limit]
        )
        return [
            {
                "urlPath": row["url_path"] or "/",
                "pageTitle": row["page_title"],
                "views": int(row["views"] or 0),
            }
            for row in rows
        ]

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

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
      {filter_where}
    GROUP BY url_path
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
    if should_use_orm_fallback():
        scoped_filters = [*(filters or []), Filter("url_path", "eq", url_path)]
        rows = pageview_time_series_rows(
            website_id,
            start_date,
            end_date,
            safe_identifier(granularity, GRANULARITIES, "day"),
            scoped_filters,
        )
        return [{"time": row["time"], "views": row["pageviews"]} for row in rows]

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)
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
        }
        for row in rows
    ]
