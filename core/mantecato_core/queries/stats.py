"""Website statistics queries — overview metrics, time series, top pages, referrers, events.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

import re as _re
from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import (
    GRANULARITIES,
    Filter,
    build_filter_sql,
    prepare_filters,
    safe_identifier,
)

# -- URL normalisation regex patterns -----------------------------------------
# Each tuple is (compiled_regex, replacement_string).  Applied sequentially to
# collapse dynamic URL segments into "/:id" for cleaner Top Pages reports.

_PATTERNS_SMART = [
    # Full UUID (8-4-4-4-12 hex format, case-insensitive).
    (_re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", _re.I), "/:id"),
    # Long hex strings (12+ chars) -- catches short UUIDs, MongoDB ObjectIds, etc.
    (_re.compile(r"/[0-9a-f]{12,}", _re.I), "/:id"),
    # Pure numeric segments -- catches integer primary keys (e.g. /posts/42).
    (_re.compile(r"/\d+"), "/:id"),
]

_PATTERNS_AGGRESSIVE = _PATTERNS_SMART + [
    # Any alphanumeric (plus _ and -) segment of 20+ chars -- catches Base64
    # tokens, hash-based slugs, and other opaque identifiers.
    (_re.compile(r"/[A-Za-z0-9_-]{20,}"), "/:id"),
]

_PATTERN_SETS = {
    "smart": _PATTERNS_SMART,
    "aggressive": _PATTERNS_AGGRESSIVE,
}


def _normalize_url(path: str, mode: str = "smart") -> str:
    """Collapse dynamic URL segments into a canonical placeholder ``/:id``.

    Many websites use dynamic path segments for resource identifiers --
    UUIDs (``/posts/550e8400-e29b-41d4-a716-446655440000``), numeric IDs
    (``/products/42``), or opaque slugs (``/r/aB3xKz9mNpQ2wY7``).  Without
    normalisation these would each appear as a separate "page" in analytics,
    making the Top Pages report noisy and less actionable.

    Two regex-based pattern sets are available:

    * ``"smart"`` (default) -- replaces full UUIDs, long hex strings
      (12+ chars), and pure-numeric segments.  Safe for most sites.
    * ``"aggressive"`` -- additionally replaces any alphanumeric segment
      of 20+ characters, catching Base64 tokens and hash-based slugs.
      May over-normalise on sites with long but meaningful slugs.

    The patterns are applied sequentially; the first match wins for each
    segment.  The function mutates a local copy of *path* in-place across
    iterations.

    Args:
        path: A URL path string (e.g. ``"/blog/posts/123"``).
        mode: Either ``"smart"`` or ``"aggressive"``.  Falls back to
            ``"smart"`` for unrecognised values.

    Returns:
        The normalised path with dynamic segments replaced by ``/:id``
        (e.g. ``"/blog/posts/:id"``).
    """
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
    """Aggregate website stats over a date range.

    Returns a :class:`WebsiteStats` dict with ``pageviews`` / ``visitors`` /
    ``visits`` / ``bounces`` / ``totaltime`` keys. Used by the analytics
    overview page and as the building block for period comparisons.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Two-level aggregation: the inner query groups by (session_id, visit_id)
    # to compute per-visit metrics (event count, time on site), then the
    # outer query aggregates across all visits.  This is necessary because
    # bounces and totaltime are per-visit concepts that cannot be computed
    # in a single flat GROUP BY.
    rows = raw_query(
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


def get_pageview_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Generate a time-bucketed series of pageview and visitor counts.

    This powers the main line/bar chart on the analytics dashboard.  The
    SQL strategy uses two CTEs:

    1. **buckets** -- ``generate_series`` creates one row per time bucket
       spanning the full date range, ensuring the chart has a data point
       for every interval even if traffic was zero.
    2. **data** -- aggregates ``website_event`` rows (pageviews only,
       ``event_type = 1``) into the same buckets using ``date_trunc``.

    A ``LEFT JOIN`` from *buckets* to *data* fills gaps with zeroes,
    producing a gapless series suitable for direct Chart.js consumption.

    The granularity is validated against a whitelist to prevent SQL
    injection (``date_trunc`` and ``generate_series`` accept the
    granularity as a string literal interpolated into the query).

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        granularity: One of ``"minute"``, ``"hour"``, ``"day"``,
            ``"week"``, or ``"month"``.  Invalid values fall back to
            ``"day"``.
        filters: Optional list of ``Filter`` objects to restrict results
            (e.g. by URL path, referrer, country).

    Returns:
        A list of dicts ordered by time ascending, each containing::

            {"time": "2025-05-20T00:00:00+00:00",
             "pageviews": 42,
             "visitors": 18}

        ``time`` is an ISO-8601 string.  ``pageviews`` and ``visitors``
        are integers (zero-filled for empty buckets).
    """
    filters = filters or []
    # granularity is interpolated into the query via f-string, so whitelist it.
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Map the granularity name to a PostgreSQL interval literal for
    # generate_series().  The generate_series step size must match the
    # date_trunc unit so that bucket boundaries align exactly.
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


def get_website_stats_comparison(
    website_id: str,
    cur_start: datetime,
    cur_end: datetime,
    prev_start: datetime,
    prev_end: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return :func:`get_website_stats` for the current and previous periods at once.

    Saves a network round trip on the overview (which always computes a
    period-over-period delta) by scanning both ranges in a single query.
    The two ranges are aggregated **independently** via ``UNION ALL`` with
    a ``period`` tag, so a visit straddling the boundary is counted in each
    period exactly as two separate :func:`get_website_stats` calls would --
    the result is byte-identical.

    Returns:
        ``{"current": {...}, "previous": {...}}`` where each value is the
        same five-key dict (``pageviews``/``visitors``/``visits``/
        ``bounces``/``totaltime``) returned by :func:`get_website_stats`.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""WITH visits AS (
      SELECT 'current' AS period, we.session_id, we.visit_id,
        COUNT(*) AS c, MIN(we.created_at) AS min_time, MAX(we.created_at) AS max_time
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.session_id, we.visit_id
      UNION ALL
      SELECT 'previous' AS period, we.session_id, we.visit_id,
        COUNT(*) AS c, MIN(we.created_at) AS min_time, MAX(we.created_at) AS max_time
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.session_id, we.visit_id
    )
    SELECT
      period,
      COALESCE(SUM(c), 0)::bigint AS pageviews,
      COUNT(DISTINCT session_id)::bigint AS visitors,
      COUNT(DISTINCT visit_id)::bigint AS visits,
      COALESCE(SUM(CASE WHEN c = 1 THEN 1 ELSE 0 END), 0)::bigint AS bounces,
      COALESCE(SUM(FLOOR(EXTRACT(EPOCH FROM (max_time - min_time)))), 0)::bigint AS totaltime
    FROM visits
    GROUP BY period""",
        {
            "websiteId": website_id,
            "curStart": cur_start,
            "curEnd": cur_end,
            "prevStart": prev_start,
            "prevEnd": prev_end,
            **filter_params,
        },
    )

    def _zero() -> dict[str, Any]:
        return {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0}

    out = {"current": _zero(), "previous": _zero()}
    for row in rows:
        out[row["period"]] = {
            "pageviews": int(row.get("pageviews") or 0),
            "visitors": int(row.get("visitors") or 0),
            "visits": int(row.get("visits") or 0),
            "bounces": int(row.get("bounces") or 0),
            "totaltime": int(row.get("totaltime") or 0),
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

    Each period keeps its own gapless ``generate_series`` bucket grid and
    ``LEFT JOIN`` gap-fill, then the two are concatenated with ``UNION ALL``
    and a ``period`` tag.  Each resulting series is byte-identical to a
    standalone :func:`get_pageview_time_series` call for that range.

    Returns:
        ``{"current": [...], "previous": [...]}`` with the same
        ``{"time", "pageviews", "visitors"}`` row shape.
    """
    filters = filters or []
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    filter_where, filter_params, session_join = prepare_filters(filters)
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
        COUNT(*)::bigint AS pageviews,
        COUNT(DISTINCT we.session_id)::bigint AS visitors
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{curStart::timestamptz}} AND {{curEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY 1
    ),
    prev_data AS (
      SELECT date_trunc('{gran}', we.created_at) AS time,
        COUNT(*)::bigint AS pageviews,
        COUNT(DISTINCT we.session_id)::bigint AS visitors
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{prevStart::timestamptz}} AND {{prevEnd::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY 1
    )
    SELECT 'current' AS period, b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews,
      COALESCE(d.visitors, 0)::bigint AS visitors
    FROM cur_buckets b LEFT JOIN cur_data d ON d.time = b.time
    UNION ALL
    SELECT 'previous' AS period, b.time,
      COALESCE(d.pageviews, 0)::bigint AS pageviews,
      COALESCE(d.visitors, 0)::bigint AS visitors
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
                "visitors": int(row["visitors"] or 0),
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
    """Return the most-viewed pages ranked by total pageview count.

    This powers the "Top Pages" widget on the analytics dashboard.  Two
    display modes are supported:

    * ``page_mode="path"`` (default) -- groups by the raw ``url_path``
      column as stored by the tracker.
    * ``page_mode="slug"`` -- strips query strings and trailing slashes
      before grouping.  When combined with ``normalize_urls``, dynamic
      segments (numeric IDs, UUIDs, hashes) are collapsed into ``/:id``
      via ``_normalize_url``, merging pages like ``/blog/123`` and
      ``/blog/456`` into a single ``/blog/:id`` row.

    **Over-fetch strategy**: when slug normalisation is active, the SQL
    fetches ``limit * 10`` rows from the database to ensure that the
    Python-side merge step (which combines rows sharing the same
    normalised path) still produces at least ``limit`` final results.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        limit: Maximum number of pages to return (default 10).
        filters: Optional ``Filter`` list (URL path, referrer, etc.).
        page_mode: ``"path"`` for raw paths or ``"slug"`` for cleaned
            paths with trailing-slash and query-string removal.
        normalize_urls: Controls dynamic-segment normalisation.
            ``True`` or ``"smart"`` collapses UUIDs/numbers;
            ``"aggressive"`` also collapses long alphanumeric tokens;
            ``False`` disables normalisation entirely.

    Returns:
        A list of dicts sorted by views descending, each containing::

            {"urlPath": "/blog/:id", "views": 320, "visitors": 185}
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    if page_mode == "slug":
        # Strip query string (everything after '?') and trailing slashes,
        # then handle the edge case where the result is empty (root path)
        # by mapping it back to '/'.
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        url_select = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        url_select = "we.url_path"

    rows = raw_query(
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
    LIMIT {limit * 10 if (page_mode == "slug" and normalize_urls) else limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    if page_mode == "slug" and normalize_urls:
        # Python-side merge: normalise each path, then sum views/visitors
        # for paths that collapse to the same canonical form.
        merged: dict[str, dict[str, int]] = {}
        for row in rows:
            norm_mode = normalize_urls if isinstance(normalize_urls, str) else "smart"
            key = _normalize_url(row["url_path"], norm_mode)
            if key in merged:
                merged[key]["views"] += int(row["views"] or 0)
                merged[key]["visitors"] += int(row["visitors"] or 0)
            else:
                merged[key] = {
                    "views": int(row["views"] or 0),
                    "visitors": int(row["visitors"] or 0),
                }
        result_list = [{"urlPath": path, **vals} for path, vals in merged.items()]
        result_list.sort(key=lambda x: x["views"], reverse=True)
        return result_list[:limit]

    return [
        {
            "urlPath": row["url_path"],
            "views": int(row["views"] or 0),
            "visitors": int(row["visitors"] or 0),
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
    """Return the most-viewed URL path sections (directory prefixes).

    While ``get_top_pages`` reports individual pages, this function groups
    traffic by the first *N* path segments -- effectively treating URL
    prefixes as "sections" of the site.  For example, with ``depth=2``,
    ``/blog/2025/hello`` and ``/blog/2025/world`` both roll up into
    ``/blog/2025``.

    The SQL strategy:

    1. Clean each ``url_path`` by stripping query strings, fragments, and
       trailing slashes.
    2. Split the cleaned path on ``/`` and take the first ``depth + 1``
       elements (PostgreSQL array slice ``[1:depth+1]``), then rejoin
       with ``/``.  The ``+1`` accounts for the leading empty string
       before the first ``/``.
    3. ``NULLIF(..., '')`` handles the root path edge case, mapping an
       empty result to ``/``.
    4. Group by the derived section and count views, visitors, and
       distinct pages.

    Like ``get_top_pages``, an over-fetch-then-merge strategy is used
    when URL normalisation is active.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        depth: Number of path segments to keep (default 2).  ``depth=1``
            gives top-level directories (``/blog``, ``/docs``), ``depth=2``
            adds one more level (``/blog/2025``, ``/docs/api``).
        limit: Maximum number of sections to return (default 10).
        filters: Optional ``Filter`` list.
        normalize_urls: Same semantics as ``get_top_pages`` -- controls
            dynamic-segment collapsing in the Python-side merge step.

    Returns:
        A list of dicts sorted by views descending, each containing::

            {"section": "/blog", "views": 1200, "visitors": 450, "pages": 38}

        ``pages`` is the count of distinct raw URL paths within the section.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # slice_end = depth + 1 because the path "/a/b/c" splits into
    # ["", "a", "b", "c"] -- the leading empty string occupies index 1.
    slice_end = depth + 1
    # Strip query string (?...) and fragment (#...) and trailing slashes
    # to get a clean path for splitting.
    clean_url = "REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(we.url_path, '?', 1), '#', 1), '/+$', '')"

    # Split the clean path into an array on '/', take the first slice_end
    # elements, rejoin with '/', and fall back to '/' for the root path.
    section_expr = (
        f"COALESCE(NULLIF(array_to_string("
        f"(string_to_array({clean_url}, '/'))[1:{slice_end}], '/'), ''), '/')"
    )

    rows = raw_query(
        f"""SELECT
      {section_expr} AS section,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(DISTINCT we.url_path)::bigint AS pages
    FROM website_event we
    {session_join}
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
                "visitors": int(row["visitors"] or 0),
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
            merged[key]["visitors"] += int(row["visitors"] or 0)
            merged[key]["pages"] += int(row["pages"] or 0)
        else:
            merged[key] = {
                "views": int(row["views"] or 0),
                "visitors": int(row["visitors"] or 0),
                "pages": int(row["pages"] or 0),
            }

    result_list = [{"section": section, **vals} for section, vals in merged.items()]
    result_list.sort(key=lambda x: x["views"], reverse=True)
    return result_list[:limit]


def get_top_referrers(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return external domains that sent the most visitors, ranked by unique visitors.

    This powers the "Top Referrers" widget.  The query counts distinct
    ``session_id`` values (unique visitors) and total pageviews per
    referring domain.  Results are ordered by visitors rather than
    pageviews because a single visitor from a referrer may generate many
    pageviews, and visitor count better reflects the referrer's reach.

    Referrer normalisation: the ``www.`` prefix is stripped via
    ``REGEXP_REPLACE`` so that ``www.google.com`` and ``google.com``
    are merged into a single row.

    Rows with a NULL or empty ``referrer_domain`` (direct traffic,
    bookmarks, or missing Referer header) are excluded -- they belong
    in the "Direct / None" bucket shown separately by the dashboard.

    Self-referrers (where the referring domain is the same as the page
    hostname) are also excluded, matching Umami's behaviour: internal
    navigation should not appear as an external referrer.  The ``www.``
    prefix is stripped on both sides of the comparison so that
    ``www.example.com`` and ``example.com`` are treated as the same host.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        limit: Maximum number of referrers to return (default 10).
        filters: Optional ``Filter`` list.

    Returns:
        A list of dicts sorted by visitors descending, each containing::

            {"referrerDomain": "google.com", "visitors": 210, "pageviews": 580}
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Strip "www." prefix so that www.google.com and google.com merge.
    _norm_ref = "REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')"
    _norm_host = "REGEXP_REPLACE(we.hostname, '^www\\.', '')"
    rows = raw_query(
        f"""SELECT
      {_norm_ref} AS referrer_domain,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.referrer_domain IS NOT NULL
      AND we.referrer_domain != ''
      AND {_norm_ref} != COALESCE({_norm_host}, '')
      {filter_where}
    GROUP BY 1
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


def get_top_events(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return the most-fired custom events ranked by total count.

    Custom events (``event_type = 2``) are user-defined actions tracked
    via the JavaScript tracker's ``track()`` call or the
    ``data-mantecato-event`` HTML attribute.  Examples include
    ``"signup_click"``, ``"purchase"``, ``"download_pdf"``.

    The query groups by ``event_name`` and counts total firings and
    distinct visitors.  Rows with a NULL ``event_name`` are excluded
    (these would be malformed tracker payloads).

    This function is also used internally by ``get_top_events_with_properties``
    as the first step to identify which events to enrich with property data.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        limit: Maximum number of events to return (default 10).
        filters: Optional ``Filter`` list.

    Returns:
        A list of dicts sorted by count descending, each containing::

            {"eventName": "signup_click", "count": 95, "visitors": 78}
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
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


def get_top_events_with_properties(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    properties_limit: int = 3,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return top events enriched with their most-common property key-value pairs.

    This is the "drill-down" companion to ``get_top_events``.  It first
    fetches the top events (delegating to ``get_top_events``), then runs
    a second query against the ``event_data`` table to find the most
    frequent ``(data_key, value)`` combinations for each event name.

    The SQL strategy uses a ``ROW_NUMBER()`` window function partitioned
    by ``event_name`` and ordered by ``COUNT(*) DESC`` to pick the top
    *N* property rows per event in a single query, avoiding N+1 round
    trips.

    The ``event_data`` table stores typed values in separate columns
    (``string_value``, ``number_value``); the query coalesces them into
    a single text ``value`` for display.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        limit: Maximum number of top-level events (default 10).
        properties_limit: Maximum number of property rows to attach to
            each event (default 3).
        filters: Optional ``Filter`` list (applied only to the event
            query, not the property enrichment query).

    Returns:
        The same list as ``get_top_events``, but each dict also contains
        a ``"properties"`` key with a list of dicts::

            {"eventName": "purchase",
             "count": 95,
             "visitors": 78,
             "properties": [
                 {"key": "plan", "value": "pro", "count": 60},
                 {"key": "plan", "value": "free", "count": 30},
                 {"key": "currency", "value": "USD", "count": 55},
             ]}

        Events with no recorded properties get an empty list.
    """
    events = get_top_events(website_id, start_date, end_date, limit, filters)
    if not events:
        return events

    # Collect event names to use as a filter in the properties query.
    # The ANY({{eventNames::text[]}}) clause matches all of them in one query.
    event_names = [e["eventName"] for e in events]

    # Single query to fetch top-N properties for ALL events at once.
    # ROW_NUMBER() partitioned by event_name avoids N+1 queries.
    rows = raw_query(
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

    # Group the flat property rows into a dict keyed by event name,
    # so we can attach them to each event in O(1) below.
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

    # Attach properties to each event dict, defaulting to [] for events
    # that had no recorded event_data rows.
    for event in events:
        event["properties"] = props_by_event.get(event["eventName"], [])

    return events


def get_country_breakdown(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return visitor and pageview counts broken down by country.

    This powers the world-map choropleth (Leaflet) and the "Countries"
    table on the analytics dashboard.  Country data comes from the
    ``session`` table, which is populated at ingestion time via MaxMind
    GeoLite2-City lookups (or CDN geo-header fallback).

    Unlike most other stats functions, this query uses ``build_filter_sql``
    directly instead of ``prepare_filters`` because it performs an explicit
    ``JOIN session`` (to access ``s.country``), and the session join from
    ``prepare_filters`` would be redundant.  Rows with a NULL country
    (failed geo-lookup) are excluded.

    The country values are ISO 3166-1 alpha-2 codes (e.g. ``"US"``,
    ``"IT"``, ``"DE"``), which the frontend maps to country names and
    flag icons.

    Args:
        website_id: UUID of the website to query.
        start_date: Inclusive lower bound (UTC).
        end_date: Inclusive upper bound (UTC).
        limit: Maximum number of countries to return (default 10).
        filters: Optional ``Filter`` list.

    Returns:
        A list of dicts sorted by visitors descending, each containing::

            {"country": "US", "visitors": 1200, "pageviews": 3400}
    """
    filters = filters or []
    # Use build_filter_sql directly (not prepare_filters) because this
    # query already has an explicit JOIN on the session table.
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    rows = raw_query(
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
