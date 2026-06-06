"""Website statistics queries — aggregate pageview metrics and time series.

Privacy-first: only aggregate pageview counts. No visitor, session, bounce,
or time-on-site metrics (those require persistent identifiers).
"""

from __future__ import annotations

import re as _re
from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import (
    GRANULARITIES,
    Filter,
    safe_identifier,
)

# -- URL normalisation regex patterns -----------------------------------------
_PATTERNS_SMART = [
    (_re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", _re.I), "/:id"),
    (_re.compile(r"/[0-9a-f]{12,}", _re.I), "/:id"),
    (_re.compile(r"/\d+"), "/:id"),
]

_PATTERNS_AGGRESSIVE = _PATTERNS_SMART + [
    (_re.compile(r"/[A-Za-z0-9_-]{20,}"), "/:id"),
]

_PATTERN_SETS = {
    "smart": _PATTERNS_SMART,
    "aggressive": _PATTERNS_AGGRESSIVE,
}


def _normalize_url(path: str, mode: str = "smart") -> str:
    """Collapse dynamic URL segments into a canonical placeholder ``/:id``."""
    patterns = _PATTERN_SETS.get(mode, _PATTERNS_SMART)
    for pat, repl in patterns:
        path = pat.sub(repl, path)
    return path


def get_first_event_date(website_id: str) -> datetime | None:
    """Return the timestamp of the first event ever recorded for *website_id*."""
    rows = raw_query(
        """SELECT MIN(created_at) AS first_event
        FROM website_event
        WHERE website_id = {{websiteId::uuid}}""",
        {"websiteId": website_id},
    )
    if rows and rows[0].get("first_event"):
        return rows[0]["first_event"]
    return None


def get_website_stats(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Aggregate website stats over a date range — pageviews only.

    Returns a dict with ``pageviews`` count. The product does not
    track visitors, sessions, bounces, or time-on-site (those require
    persistent identifiers).
    """
    filters = filters or []

    rows = raw_query(
        """SELECT
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    row = rows[0] if rows else {}
    return {
        "pageviews": int(row.get("pageviews") or 0),
    }


def get_pageview_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Generate a time-bucketed series of pageview counts.

    Uses ``generate_series`` for gapless time buckets and ``date_trunc``
    for aggregation. Only pageview counts (no visitors) are returned.
    """
    filters = filters or []
    gran = safe_identifier(granularity, GRANULARITIES, "day")

    gran_interval = {
        "minute": "1 minute",
        "hour": "1 hour",
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
    }.get(gran, "1 day")

    rows = raw_query(
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
        COUNT(*)::bigint AS pageviews
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
      GROUP BY 1
    )
    SELECT
      b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews
    FROM buckets b
    LEFT JOIN data d ON d.time = b.time
    ORDER BY b.time ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]


def get_website_stats_comparison(
    website_id: str,
    cur_start: datetime,
    cur_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return :func:`get_website_stats` for the current and previous periods at once.

    Returns ``{"current": {...}, "previous": {...}}`` where each value
    contains ``pageviews`` count.
    """
    filters = filters or []

    rows = raw_query(
        """SELECT 'current' AS period,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
      AND we.event_type = 1
    UNION ALL
    SELECT 'previous' AS period,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
      AND we.event_type = 1""",
        {
            "websiteId": website_id,
            "curStart": cur_start,
            "curEnd": cur_end,
            "prevStart": prev_start,
            "prevEnd": prev_end,
        },
    )

    def _zero() -> dict[str, Any]:
        return {"pageviews": 0}

    out: dict[str, dict[str, Any]] = {"current": _zero(), "previous": _zero()}
    for row in rows:
        out[row["period"]] = {
            "pageviews": int(row.get("pageviews") or 0),
        }
    return out


def get_pageview_time_series_comparison(
    website_id: str,
    cur_start: datetime,
    cur_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return :func:`get_pageview_time_series` for current + previous in one query.

    Returns ``{"current": [...], "previous": [...]}`` with ``{"time", "pageviews"}``
    row shape.
    """
    filters = filters or []
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    gran_interval = {
        "minute": "1 minute",
        "hour": "1 hour",
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
    }.get(gran, "1 day")

    rows = raw_query(
        f"""WITH cur_buckets AS (
      SELECT generate_series(
        date_trunc('{gran}', {{curStart::timestamptz}}),
        date_trunc('{gran}', {{curEnd::timestamptz}}),
        '{gran_interval}'::interval
      ) AS time
    ),
    prev_buckets AS (
      SELECT generate_series(
        date_trunc('{gran}', {{prevStart::timestamptz}}),
        date_trunc('{gran}', {{prevEnd::timestamptz}}),
        '{gran_interval}'::interval
      ) AS time
    ),
    cur_data AS (
      SELECT date_trunc('{gran}', we.created_at) AS time,
        COUNT(*)::bigint AS pageviews
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
        AND we.event_type = 1
      GROUP BY 1
    ),
    prev_data AS (
      SELECT date_trunc('{gran}', we.created_at) AS time,
        COUNT(*)::bigint AS pageviews
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
        AND we.event_type = 1
      GROUP BY 1
    )
    SELECT 'current' AS period, b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews
    FROM cur_buckets b LEFT JOIN cur_data d ON d.time = b.time
    UNION ALL
    SELECT 'previous' AS period, b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews
    FROM prev_buckets b LEFT JOIN prev_data d ON d.time = b.time
    ORDER BY period, time ASC""",
        {
            "websiteId": website_id,
            "curStart": cur_start,
            "curEnd": cur_end,
            "prevStart": prev_start,
            "prevEnd": prev_end,
        },
    )

    out: dict[str, list[dict[str, Any]]] = {"current": [], "previous": []}
    for row in rows:
        out[row["period"]].append(
            {
                "time": row["time"].isoformat()
                if isinstance(row["time"], datetime)
                else str(row["time"]),
                "pageviews": int(row["pageviews"] or 0),
            }
        )
    return out


def get_top_pages(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
    page_mode: str = "path",
    normalize_urls: bool | str = True,
) -> list[dict[str, Any]]:
    """Return the most-viewed pages ranked by total pageview count."""
    filters = filters or []

    if page_mode == "slug":
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        url_select = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        url_select = "we.url_path"

    rows = raw_query(
        f"""SELECT
      {url_select} AS url_path,
      COUNT(*)::bigint AS views
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
    GROUP BY url_path
    ORDER BY views DESC
    LIMIT {limit * 10 if (page_mode == 'slug' and normalize_urls) else limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    if page_mode == "slug" and normalize_urls:
        merged: dict[str, dict[str, int]] = {}
        for row in rows:
            norm_mode = normalize_urls if isinstance(normalize_urls, str) else "smart"
            key = _normalize_url(row["url_path"], norm_mode)
            if key in merged:
                merged[key]["views"] += int(row["views"] or 0)
            else:
                merged[key] = {"views": int(row["views"] or 0)}
        result_list = [{"urlPath": path, **vals} for path, vals in merged.items()]
        result_list.sort(key=lambda x: x["views"], reverse=True)
        return result_list[:limit]

    return [
        {
            "urlPath": row["url_path"],
            "views": int(row["views"] or 0),
        }
        for row in rows[:limit]
    ]


def get_top_sections(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    depth: int = 2,
    limit: int = 10,
    filters: list[Filter] | None = None,
    normalize_urls: bool | str = True,
) -> list[dict[str, Any]]:
    """Return the most-viewed URL path sections (directory prefixes)."""
    filters = filters or []

    slice_end = depth + 1
    clean_url = "REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(we.url_path, '?', 1), '#', 1), '/+$', '')"
    section_expr = (
        f"COALESCE(NULLIF(array_to_string("
        f"(string_to_array({clean_url}, '/'))[1:{slice_end}], '/'), ''), '/')"
    )

    rows = raw_query(
        f"""SELECT
      {section_expr} AS section,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.url_path)::bigint AS pages
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
    GROUP BY 1
    ORDER BY views DESC
    LIMIT {limit * 10 if normalize_urls else limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    if not normalize_urls:
        return [
            {
                "section": row["section"],
                "views": int(row["views"] or 0),
                "pages": int(row["pages"] or 0),
            }
            for row in rows
        ]

    merged: dict[str, dict[str, int]] = {}
    for row in rows:
        norm_mode = normalize_urls if isinstance(normalize_urls, str) else "smart"
        key = _normalize_url(row["section"], norm_mode)
        if key in merged:
            merged[key]["views"] += int(row["views"] or 0)
            merged[key]["pages"] += int(row["pages"] or 0)
        else:
            merged[key] = {
                "views": int(row["views"] or 0),
                "pages": int(row["pages"] or 0),
            }

    result_list = [{"section": section, **vals} for section, vals in merged.items()]
    result_list.sort(key=lambda x: x["views"], reverse=True)
    return result_list[:limit]


def get_country_breakdown(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return pageview counts broken down by country.

    Country data comes directly from the website_event
    table (no session join needed).
    """
    filters = filters or []

    rows = raw_query(
        f"""SELECT
      we.country,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.country IS NOT NULL
    GROUP BY we.country
    ORDER BY pageviews DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    return [
        {
            "country": row["country"],
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]
