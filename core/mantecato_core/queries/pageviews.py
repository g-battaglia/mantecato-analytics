"""Page-level analytics queries — metrics, referrers, navigation, time distribution, time series.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters


def get_page_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    page_mode: str = "path",
) -> list[dict[str, Any]]:
    """Compute comprehensive per-page engagement metrics with pagination.

    Produces a ranked table of pages with views, visitors, time on page,
    entry/exit counts, and bounce rate.  Supports two URL normalization
    modes controlled by ``page_mode``:

    - ``"path"`` (default): uses the raw ``url_path`` as stored by the
      tracker, including query strings.
    - ``"slug"``: strips query strings and trailing slashes, collapsing
      ``/blog/post/?ref=twitter`` and ``/blog/post/`` into ``/blog/post``.
      Empty paths after stripping are mapped to ``/``.

    The query uses three CTEs for correctness and performance:

    1. **filtered_events** -- applies time/filter constraints and URL
       normalization once, avoiding repeated expression evaluation.
    2. **page_sequence** -- uses ``LEAD()`` to find the next page
       timestamp (for time-on-page calculation) and ``ROW_NUMBER()`` in
       both ASC and DESC order to identify entry pages (``rn_entry = 1``)
       and exit pages (``rn_exit = 1``) within each visit.
    3. **visit_bounces** -- counts pages per visit to identify bounces
       (visits with exactly one pageview).

    Time on page is computed as the difference between the current
    page's timestamp and the next page's timestamp.  The last page in a
    visit has ``next_page_at = NULL`` (exit page), so it is excluded
    from time-on-page calculations via FILTER clauses.

    Bounce rate is scoped to *entry pages only*: it is the ratio of
    single-page visits entering on a given page to all visits entering
    on that page.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of page rows per page of results (default 50).
        offset: Row offset for pagination (default 0).
        filters: Optional list of column filters to narrow the dataset.
        page_mode: URL normalization mode -- ``"path"`` or ``"slug"``.

    Returns:
        List of dicts, each containing:
        - ``urlPath`` (str): The (possibly normalized) URL path.
        - ``pageTitle`` (str | None): Most recent page title seen.
        - ``views`` (int): Total pageview count.
        - ``visitors`` (int): Unique session count.
        - ``avgTimeOnPage`` (float | None): Mean seconds spent on page.
        - ``medianTimeOnPage`` (float | None): Median (p50) seconds on page.
        - ``entries`` (int): Number of visits that started on this page.
        - ``exits`` (int): Number of visits that ended on this page.
        - ``bounceRate`` (float): Bounce percentage for visits entering
          on this page.
        Sorted by views descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join_cte = prepare_filters(filters)

    # In "slug" mode we strip query strings (SPLIT_PART on '?') and
    # trailing slashes (REGEXP_REPLACE), then coalesce empty string to '/'
    # so the root path is always represented consistently.
    if page_mode == "slug":
        url_expr = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
        slug_coalesce = f"CASE WHEN {url_expr} = '' THEN '/' ELSE {url_expr} END"
    else:
        url_expr = "we.url_path"
        slug_coalesce = url_expr

    rows = raw_query(
        f"""WITH filtered_events AS (
      SELECT {slug_coalesce} AS url_path, we.page_title, we.visit_id, we.session_id, we.created_at
      FROM website_event we
      {session_join_cte}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    ),
    page_sequence AS (
      SELECT
        url_path,
        page_title,
        visit_id,
        session_id,
        created_at,
        LEAD(created_at) OVER (PARTITION BY visit_id ORDER BY created_at) AS next_page_at,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at ASC) AS rn_entry,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at DESC) AS rn_exit
      FROM filtered_events
    ),
    visit_bounces AS (
      SELECT visit_id, COUNT(*) AS page_count
      FROM filtered_events
      GROUP BY visit_id
    )
    SELECT
      ps.url_path,
      MAX(ps.page_title) AS page_title,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT ps.session_id)::bigint AS visitors,
      AVG(EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at)))
        FILTER (WHERE ps.next_page_at IS NOT NULL) AS avg_time_on_page,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ps.next_page_at - ps.created_at))
      ) FILTER (WHERE ps.next_page_at IS NOT NULL) AS median_time_on_page,
      COUNT(*) FILTER (WHERE ps.rn_entry = 1)::bigint AS entries,
      COUNT(*) FILTER (WHERE ps.rn_exit = 1)::bigint AS exits,
      CASE
        WHEN COUNT(*) FILTER (WHERE ps.rn_entry = 1) = 0 THEN 0
        ELSE (
          COUNT(*) FILTER (WHERE ps.rn_entry = 1 AND vb.page_count = 1)::float /
          NULLIF(COUNT(*) FILTER (WHERE ps.rn_entry = 1), 0) * 100
        )
      END AS bounce_rate
    FROM page_sequence ps
    LEFT JOIN visit_bounces vb ON ps.visit_id = vb.visit_id
    GROUP BY ps.url_path
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
            "visitors": int(row["visitors"] or 0),
            "avgTimeOnPage": row["avg_time_on_page"],
            "medianTimeOnPage": row["median_time_on_page"],
            "entries": int(row["entries"] or 0),
            "exits": int(row["exits"] or 0),
            "bounceRate": row["bounce_rate"] or 0,
        }
        for row in rows
    ]


def get_page_referrers(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """List the top referrer domains that sent traffic to a specific page.

    Provides a drill-down from the page metrics table: for a given
    ``url_path``, shows which referrer domains drove the most visitors.
    Referrer domains are normalized by stripping the ``www.`` prefix,
    and NULL/empty referrers are reported as ``(direct)``.

    No session JOIN is needed here because all data comes from the
    ``website_event`` table (no device/geo filters supported in this
    simplified drill-down view).

    Args:
        website_id: UUID of the tracked website.
        url_path: Exact URL path to filter by.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of referrer rows to return (default 10).

    Returns:
        List of dicts, each containing:
        - ``referrerDomain`` (str): Normalized referrer domain or
          ``(direct)``.
        - ``visitors`` (int): Unique session count.
        - ``views`` (int): Total pageview count.
        Sorted by visitors descending.
    """
    # Self-referrers (same domain as the page hostname) are excluded so
    # internal navigation doesn't pollute the per-page referrer drill-down.
    # NULL referrers are still kept and reported as '(direct)'.
    rows = raw_query(
        f"""SELECT
      COALESCE(NULLIF(
        REGEXP_REPLACE(we.referrer_domain, '^www\\.', ''), ''
      ), '(direct)') AS referrer_domain,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS views
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.url_path = {{urlPath}}
      AND (
        we.referrer_domain IS NULL
        OR REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')
           != COALESCE(REGEXP_REPLACE(we.hostname, '^www\\.', ''), '')
      )
    GROUP BY 1
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    return [
        {
            "referrerDomain": row["referrer_domain"],
            "visitors": int(row["visitors"] or 0),
            "views": int(row["views"] or 0),
        }
        for row in rows
    ]


def get_next_pages(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find the most common pages visitors navigate to after viewing a given page.

    Uses a ``LEAD()`` window function partitioned by ``visit_id`` and
    ordered by timestamp to determine the immediate next page in each
    visit.  Self-transitions (same page to same page, e.g. from a
    reload) are excluded, as are visits where the current page was
    the exit page (``next_url IS NULL``).

    Each result row includes a ``percentage`` field computed client-side
    (in Python) as the fraction of all "next page" navigations from
    the given page.

    Args:
        website_id: UUID of the tracked website.
        url_path: The source page whose outbound navigation to analyze.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of destination pages to return (default 10).

    Returns:
        List of dicts, each containing:
        - ``urlPath`` (str): The destination page URL path.
        - ``count`` (int): Number of transitions to this page.
        - ``percentage`` (float): Percentage of all transitions from
          the source page to this destination.
        Sorted by count descending.
    """
    # CTE orders all pageviews within each visit chronologically and uses
    # LEAD() to peek at the next page.  Outer WHERE filters to navigations
    # FROM the target page, excludes exits (next_url IS NULL) and reloads
    # (next_url = current page).
    rows = raw_query(
        f"""WITH page_nav AS (
      SELECT
        we.url_path,
        we.visit_id,
        we.created_at,
        LEAD(we.url_path) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) AS next_url
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
    )
    SELECT
      next_url,
      COUNT(*)::bigint AS count
    FROM page_nav
    WHERE url_path = {{urlPath}}
      AND next_url IS NOT NULL
      AND next_url != {{urlPath}}
    GROUP BY next_url
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    # Compute percentages in Python rather than SQL because the total is
    # needed across all returned rows (not just a window within the query).
    total = sum(int(r["count"] or 0) for r in rows)
    return [
        {
            "urlPath": row["next_url"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


def get_time_on_page_distribution(
    website_id: str,
    url_path: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Compute a histogram of time spent on a specific page.

    Calculates the time a visitor spent on a page by taking the
    difference between the page's timestamp and the next page's
    timestamp within the same visit (using ``LEAD()``).  The last page
    in a visit has no "next" page, so its duration is NULL, bucketed
    as ``"Exit"``.

    Duration values are classified into human-readable buckets:
    ``0-5s``, ``5-15s``, ``15-30s``, ``30-60s``, ``1-2m``, ``2-5m``,
    ``5m+``, and ``Exit``.  Buckets are returned in ascending order
    (shortest to longest) with ``Exit`` always last.

    The ORDER BY uses a MIN of a synthetic ordinal (CASE expression)
    to ensure deterministic bucket ordering regardless of which
    buckets have data.

    Args:
        website_id: UUID of the tracked website.
        url_path: Exact URL path to analyze.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.

    Returns:
        List of dicts, each containing:
        - ``bucket`` (str): The duration range label (e.g. ``"5-15s"``).
        - ``count`` (int): Number of pageviews falling into this bucket.
        Ordered by bucket from shortest to longest, with ``Exit`` last.
    """
    rows = raw_query(
        """WITH page_durations AS (
      SELECT
        EXTRACT(EPOCH FROM (
          LEAD(we.created_at) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) - we.created_at
        )) AS duration_sec
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND we.url_path = {{urlPath}}
    )
    SELECT
      CASE
        WHEN duration_sec IS NULL THEN 'Exit'
        WHEN duration_sec < 5 THEN '0-5s'
        WHEN duration_sec < 15 THEN '5-15s'
        WHEN duration_sec < 30 THEN '15-30s'
        WHEN duration_sec < 60 THEN '30-60s'
        WHEN duration_sec < 120 THEN '1-2m'
        WHEN duration_sec < 300 THEN '2-5m'
        ELSE '5m+'
      END AS bucket,
      COUNT(*)::bigint AS count
    FROM page_durations
    GROUP BY 1
    ORDER BY MIN(CASE
        WHEN duration_sec IS NULL THEN 8
        WHEN duration_sec < 5 THEN 1
        WHEN duration_sec < 15 THEN 2
        WHEN duration_sec < 30 THEN 3
        WHEN duration_sec < 60 THEN 4
        WHEN duration_sec < 120 THEN 5
        WHEN duration_sec < 300 THEN 6
        ELSE 7
      END)""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "urlPath": url_path,
        },
    )

    return [
        {
            "bucket": row["bucket"],
            "count": int(row["count"] or 0),
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
    """Generate a time series of views and visitors for a specific page.

    Uses ``date_trunc()`` to bucket events into time intervals at the
    requested granularity, producing one data point per interval.
    Intervals with no traffic are not included in the result (the
    frontend fills gaps when rendering the chart).

    The ``granularity`` parameter is validated against a whitelist and
    falls back to ``"day"`` if an invalid value is provided, preventing
    both SQL injection and unexpected query plans from unusual truncation
    levels.

    Args:
        website_id: UUID of the tracked website.
        url_path: Exact URL path to generate the series for.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        granularity: Time bucket size -- one of ``"minute"``,
            ``"hour"``, ``"day"``, ``"week"``, or ``"month"``.
            Defaults to ``"day"`` if invalid.
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts ordered chronologically, each containing:
        - ``time`` (str): ISO 8601 timestamp of the bucket start.
        - ``views`` (int): Total pageview count in this bucket.
        - ``visitors`` (int): Unique session count in this bucket.
    """
    filters = filters or []
    # Whitelist validation: granularity is interpolated into the SQL string
    # via f-string (inside date_trunc), so invalid values must be rejected.
    valid_granularities = ["minute", "hour", "day", "week", "month"]
    gran = granularity if granularity in valid_granularities else "day"
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS views,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM website_event we
    {session_join}
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
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]
