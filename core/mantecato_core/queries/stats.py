"""Website statistics queries — pageview metrics, time series, and exact counts.

Cookieless: pageview aggregates come from ``website_event``; exact
visitor/visit/bounce/duration metrics come from the compute-and-discard
aggregates (see :mod:`core.mantecato_core.visitor_counting`). No persistent
per-person identifier is stored.
"""

from __future__ import annotations

import re as _re
from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import (
    GRANULARITIES,
    Filter,
    prepare_filters,
    safe_identifier,
)
from core.mantecato_core.queries.orm_fallbacks import (
    pageview_queryset,
    pageview_time_series_rows,
    should_use_orm_fallback,
    stats_dict,
    top_sections_from_qs,
)
from core.mantecato_core.queries.visitors import (
    visit_metrics,
    visitors_by_bucket,
    visits_by_bucket,
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
    if should_use_orm_fallback():
        from apps.core.models import WebsiteEvent

        return (
            WebsiteEvent.objects.filter(website_id=website_id)
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )

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
    """Aggregate website stats over a date range.

    Returns pageview counts plus **exact** visitor/visit/bounce metrics from the
    compute-and-discard aggregates (``visitors``, ``visits``, ``bounces``,
    ``totaltime`` and the derived ``bounce_rate``/``avg_duration``/
    ``pages_per_visit``). Visitor metrics are ``None`` when a content/device/geo
    filter is active (aggregates cannot be sliced by those dimensions).
    """
    filters = filters or []

    if should_use_orm_fallback():
        base = stats_dict(pageview_queryset(website_id, start_date, end_date, filters))
    else:
        filter_where, filter_params, _ = prepare_filters(filters)
        rows = raw_query(
            """SELECT
      COUNT(*)::bigint AS pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = false)::bigint AS human_pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = true)::bigint AS bot_pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      """ + filter_where,
            {
                "websiteId": website_id,
                "startDate": start_date,
                "endDate": end_date,
                **filter_params,
            },
        )
        row = rows[0] if rows else {}
        base = {
            "pageviews": int(row.get("pageviews") or 0),
            "human_pageviews": int(row.get("human_pageviews") or 0),
            "bot_pageviews": int(row.get("bot_pageviews") or 0),
        }

    base.update(visit_metrics(website_id, start_date, end_date, filters))
    return base


def _attach_visitors(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add exact unique ``visitors`` and ``visits`` counts per bucket (any granularity)."""
    by_visitor = visitors_by_bucket(website_id, start_date, end_date, granularity)
    by_visits = visits_by_bucket(website_id, start_date, end_date, granularity)
    for row in rows:
        row["visitors"] = by_visitor.get(row["time"], 0)
        row["visits"] = by_visits.get(row["time"], 0)
    return rows


def get_pageview_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Generate a time-bucketed series of pageviews (and exact visits at day+).

    Uses ``generate_series`` for gapless time buckets and ``date_trunc`` for
    aggregation. A ``visits`` count is attached per bucket at day/week/month
    granularity (visits are a daily metric).
    """
    gran = safe_identifier(granularity, GRANULARITIES, "day")

    if should_use_orm_fallback():
        rows = pageview_time_series_rows(website_id, start_date, end_date, gran, filters)
        return _attach_visitors(website_id, start_date, end_date, gran, rows)

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)
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
        {filter_where}
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
            **filter_params,
        },
    )

    series = [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]
    return _attach_visitors(website_id, start_date, end_date, gran, series)


def get_website_stats_comparison(
    website_id: str,
    cur_start: datetime,
    cur_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return :func:`get_website_stats` for the current and previous periods at once.

    Returns ``{"current": {...}, "previous": {...}}`` where each value contains
    pageview counts plus the exact visitor/visit/bounce metrics (see
    :func:`get_website_stats`).
    """
    filters = filters or []

    def _zero() -> dict[str, Any]:
        return {"pageviews": 0, "human_pageviews": 0, "bot_pageviews": 0}

    out: dict[str, dict[str, Any]] = {"current": _zero(), "previous": _zero()}

    if should_use_orm_fallback():
        out["current"] = stats_dict(pageview_queryset(website_id, cur_start, cur_end, filters))
        out["previous"] = stats_dict(pageview_queryset(website_id, prev_start, prev_end, filters))
    else:
        filter_where, filter_params, _ = prepare_filters(filters)
        rows = raw_query(
            """SELECT 'current' AS period,
      COUNT(*)::bigint AS pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = false)::bigint AS human_pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = true)::bigint AS bot_pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
      AND we.event_type = 1
      """ + filter_where + """
    UNION ALL
    SELECT 'previous' AS period,
      COUNT(*)::bigint AS pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = false)::bigint AS human_pageviews,
      COUNT(*) FILTER (WHERE COALESCE(we.is_bot, false) = true)::bigint AS bot_pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
      AND we.event_type = 1
      """ + filter_where,
            {
                "websiteId": website_id,
                "curStart": cur_start,
                "curEnd": cur_end,
                "prevStart": prev_start,
                "prevEnd": prev_end,
                **filter_params,
            },
        )
        for row in rows:
            out[row["period"]] = {
                "pageviews": int(row.get("pageviews") or 0),
                "human_pageviews": int(row.get("human_pageviews") or 0),
                "bot_pageviews": int(row.get("bot_pageviews") or 0),
            }

    out["current"].update(visit_metrics(website_id, cur_start, cur_end, filters))
    out["previous"].update(visit_metrics(website_id, prev_start, prev_end, filters))
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
    gran = safe_identifier(granularity, GRANULARITIES, "day")

    if should_use_orm_fallback():
        return {
            "current": _attach_visitors(
                website_id, cur_start, cur_end, gran,
                pageview_time_series_rows(website_id, cur_start, cur_end, gran, filters),
            ),
            "previous": _attach_visitors(
                website_id, prev_start, prev_end, gran,
                pageview_time_series_rows(website_id, prev_start, prev_end, gran, filters),
            ),
        }

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)
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
        {filter_where}
      GROUP BY 1
    ),
    prev_data AS (
      SELECT date_trunc('{gran}', we.created_at) AS time,
        COUNT(*)::bigint AS pageviews
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
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
            **filter_params,
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
    _attach_visitors(website_id, cur_start, cur_end, gran, out["current"])
    _attach_visitors(website_id, prev_start, prev_end, gran, out["previous"])
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
    if should_use_orm_fallback():
        from django.db.models import Count

        qs = pageview_queryset(website_id, start_date, end_date, filters)
        rows = (
            qs.values("url_path")
            .annotate(views=Count("event_id"))
            .order_by("-views", "url_path")
        )
        if page_mode == "slug" and normalize_urls:
            merged: dict[str, dict[str, int]] = {}
            norm_mode = normalize_urls if isinstance(normalize_urls, str) else "smart"
            for row in rows[: limit * 10]:
                clean = (row["url_path"] or "/").split("?", 1)[0].rstrip("/") or "/"
                key = _normalize_url(clean, norm_mode)
                merged.setdefault(key, {"views": 0})["views"] += int(row["views"] or 0)
            result_list = [{"urlPath": path, **vals} for path, vals in merged.items()]
            result_list.sort(key=lambda x: x["views"], reverse=True)
            return result_list[:limit]
        return [
            {"urlPath": row["url_path"] or "/", "views": int(row["views"] or 0)}
            for row in rows[:limit]
        ]

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

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
      {filter_where}
    GROUP BY url_path
    ORDER BY views DESC
    LIMIT {limit * 10 if (page_mode == 'slug' and normalize_urls) else limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
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
    if should_use_orm_fallback():
        norm_mode = normalize_urls if isinstance(normalize_urls, str) else "smart"
        normalizer = (lambda value: _normalize_url(value, norm_mode)) if normalize_urls else None
        return top_sections_from_qs(
            pageview_queryset(website_id, start_date, end_date, filters),
            depth,
            limit,
            normalizer,
        )

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

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
      {filter_where}
    GROUP BY 1
    ORDER BY views DESC
    LIMIT {limit * 10 if normalize_urls else limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
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
    if should_use_orm_fallback():
        from django.db.models import Count

        rows = (
            pageview_queryset(website_id, start_date, end_date, filters)
            .exclude(country__isnull=True)
            .exclude(country="")
            .values("country")
            .annotate(pageviews=Count("event_id"))
            .order_by("-pageviews", "country")[:limit]
        )
        return [
            {"country": row["country"], "pageviews": int(row["pageviews"] or 0)}
            for row in rows
        ]

    filters = filters or []
    filter_where, filter_params, _ = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      we.country,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.country IS NOT NULL
      {filter_where}
    GROUP BY we.country
    ORDER BY pageviews DESC
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
            "pageviews": int(row["pageviews"] or 0),
        }
        for row in rows
    ]
