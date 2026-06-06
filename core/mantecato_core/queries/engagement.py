"""Engagement queries — duration distribution, percentiles, duration by page,
bounce rate by page, bounce rate by source, and sessions-for-bucket drilldown.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
The sub-queries in ``get_sessions_for_bucket`` run sequentially on a single
reused connection: dispatching them across a ThreadPoolExecutor opened a fresh
TLS connection per worker (and the remote Postgres serialises queries anyway),
which made the parallel variant slower than sequential — see commit bbf4728 for
the same finding on the overview path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, prepare_filters


def get_duration_distribution(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Visit duration histogram buckets."""
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id
    ),
    bucketed AS (
      SELECT
        CASE
          WHEN duration_secs = 0 THEN '0s (bounce)'
          WHEN duration_secs < 10 THEN '1-10s'
          WHEN duration_secs < 30 THEN '10-30s'
          WHEN duration_secs < 60 THEN '30s-1m'
          WHEN duration_secs < 180 THEN '1-3m'
          WHEN duration_secs < 600 THEN '3-10m'
          WHEN duration_secs < 1800 THEN '10-30m'
          ELSE '30m+'
        END AS bucket,
        CASE
          WHEN duration_secs = 0 THEN 0
          WHEN duration_secs < 10 THEN 1
          WHEN duration_secs < 30 THEN 2
          WHEN duration_secs < 60 THEN 3
          WHEN duration_secs < 180 THEN 4
          WHEN duration_secs < 600 THEN 5
          WHEN duration_secs < 1800 THEN 6
          ELSE 7
        END AS bucket_order
      FROM visit_durations
    )
    SELECT bucket, bucket_order, COUNT(*)::bigint AS visits
    FROM bucketed
    GROUP BY bucket, bucket_order
    ORDER BY bucket_order""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    total = sum(int(r["visits"] or 0) for r in rows)

    return [
        {
            "bucket": row["bucket"],
            "bucketOrder": int(row["bucket_order"] or 0),
            "visits": int(row["visits"] or 0),
            "percentage": (int(row["visits"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


def get_duration_percentiles(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Duration percentiles (p50, p75, p90, p95, p99, avg, min, max)."""
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""WITH visit_durations AS (
      SELECT
        we.visit_id,
        EXTRACT(EPOCH FROM (MAX(we.created_at) - MIN(we.created_at))) AS duration_secs
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
      GROUP BY we.visit_id
      HAVING COUNT(*) > 1
    )
    SELECT
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_secs) AS p50,
      PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_secs) AS p75,
      PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY duration_secs) AS p90,
      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_secs) AS p95,
      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_secs) AS p99,
      AVG(duration_secs) AS avg,
      MIN(duration_secs) AS min_dur,
      MAX(duration_secs) AS max_dur,
      COUNT(*)::bigint AS total_visits
    FROM visit_durations""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    row = rows[0] if rows else {}
    p50 = float(row.get("p50") or 0)

    return {
        "p50": p50,
        "p75": float(row.get("p75") or 0),
        "p90": float(row.get("p90") or 0),
        "p95": float(row.get("p95") or 0),
        "p99": float(row.get("p99") or 0),
        "avg": float(row.get("avg") or 0),
        "median": p50,
        "min": float(row.get("min_dur") or 0),
        "max": float(row.get("max_dur") or 0),
        "totalVisits": int(row.get("total_visits") or 0),
    }


def get_duration_by_page(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Avg, median, p90 duration by page."""
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""WITH page_sequence AS (
      SELECT
        we.url_path,
        we.visit_id,
        we.created_at,
        LEAD(we.created_at) OVER (PARTITION BY we.visit_id ORDER BY we.created_at) AS next_page_at
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS views,
      AVG(EXTRACT(EPOCH FROM (next_page_at - created_at)))
        FILTER (WHERE next_page_at IS NOT NULL) AS avg_duration,
      PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS median_duration,
      PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (next_page_at - created_at))
      ) FILTER (WHERE next_page_at IS NOT NULL) AS p90_duration
    FROM page_sequence
    GROUP BY url_path
    HAVING COUNT(*) FILTER (WHERE next_page_at IS NOT NULL) > 0
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
            "avgDuration": float(row["avg_duration"] or 0),
            "medianDuration": float(row["median_duration"] or 0),
            "p90Duration": float(row["p90_duration"] or 0),
        }
        for row in rows
    ]


def get_bounce_rate_by_page(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Bounce rate breakdown by entry page."""
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""WITH entry_pages AS (
      SELECT
        we.visit_id,
        we.url_path,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    )
    SELECT
      url_path,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM entry_pages
    WHERE rn = 1
    GROUP BY url_path
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
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
            "totalVisits": int(row["total_visits"] or 0),
            "bounces": int(row["bounces"] or 0),
            "bounceRate": float(row["bounce_rate"] or 0),
        }
        for row in rows
    ]


def get_bounce_rate_by_source(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Bounce rate breakdown by referrer source."""
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    # Self-referrers (referrer_domain == hostname) are excluded so that
    # internal navigation does not appear in the bounce-by-source ranking.
    # NULL referrers are kept and roll into the '(direct)' bucket.
    rows = raw_query(
        f"""WITH visit_info AS (
      SELECT
        we.visit_id,
        REGEXP_REPLACE(we.referrer_domain, '^www\\.', '') AS referrer_domain,
        ROW_NUMBER() OVER (PARTITION BY we.visit_id ORDER BY we.created_at ASC) AS rn,
        COUNT(*) OVER (PARTITION BY we.visit_id) AS pages_in_visit
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        AND (
          we.referrer_domain IS NULL
          OR REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')
             != COALESCE(REGEXP_REPLACE(we.hostname, '^www\\.', ''), '')
        )
        {filter_where}
    )
    SELECT
      COALESCE(referrer_domain, '(direct)') AS referrer_domain,
      COUNT(*)::bigint AS total_visits,
      COUNT(*) FILTER (WHERE pages_in_visit = 1)::bigint AS bounces,
      CASE WHEN COUNT(*) > 0
        THEN (COUNT(*) FILTER (WHERE pages_in_visit = 1)::float / COUNT(*)::float) * 100
        ELSE 0
      END AS bounce_rate
    FROM visit_info
    WHERE rn = 1
    GROUP BY referrer_domain
    HAVING COUNT(*) >= 2
    ORDER BY total_visits DESC
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
            "totalVisits": int(row["total_visits"] or 0),
            "bounces": int(row["bounces"] or 0),
            "bounceRate": float(row["bounce_rate"] or 0),
        }
        for row in rows
    ]


# Maps each duration bucket label to its (min_secs, max_secs) range.
# Bounce bucket uses (0, 0) -- visits with exactly zero seconds.
# The "30m+" bucket uses None as max to indicate no upper bound.
# The "1-10s" bucket starts at 0.1 (not 0) to exclude bounces.
BUCKET_RANGES: dict[str, tuple[float, float | None]] = {
    "0s (bounce)": (0, 0),
    "1-10s": (0.1, 10),
    "10-30s": (10, 30),
    "30s-1m": (30, 60),
    "1-3m": (60, 180),
    "3-10m": (180, 600),
    "10-30m": (600, 1800),
    "30m+": (1800, None),
}


def get_sessions_for_bucket(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    bucket: str,
    limit: int = 50,
    offset: int = 0,
    filters: list[Filter] | None = None,
    entry_page: str | None = None,
) -> dict[str, Any]:
    """Drill down into a specific duration bucket from the engagement histogram.

    Given a duration bucket label (e.g. ``"1-3m"``), retrieves a rich
    set of data about the visits in that bucket:

    - **sessions** -- paginated list of individual visits with geo/device
      metadata and landing page info.
    - **countries** / **cities** -- geographic distribution of visits.
    - **pages** -- most viewed pages within these visits.
    - **entryPages** -- most common landing pages.
    - **journeys** -- most common page navigation paths (up to 4 steps).
    - **sources** -- referrer domain distribution.
    - **devices** -- browser/OS/device breakdown.

    This function is the most complex in the engagement module.  It
    uses a shared base CTE (``base_cte``) containing four sub-CTEs
    that all subsequent queries build upon:

    1. **filtered_events** -- all pageviews in the time range, with
       URL normalization and filter application.
    2. **visit_entries** -- determines the entry (landing) page and
       entry referrer for each visit using ``DISTINCT ON`` ordered
       by timestamp.
    3. **bucket_visits** -- aggregates per-visit stats (page count,
       duration, start time).
    4. **bucket_scope** -- joins bucket_visits with visit_entries and
       applies the duration range filter and optional entry page
       filter, producing the final set of visits in scope.

    To minimize latency, nine sub-queries are dispatched concurrently
    via a ``ThreadPoolExecutor`` with 6 workers.  Each worker runs
    the shared base CTE plus a specific aggregation query.  The
    ``_q()`` helper and ``_db_call()`` wrapper ensure that Django
    database connections are properly managed in worker threads.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        bucket: Duration bucket label to drill into.  Must match a key
            in ``BUCKET_RANGES`` (e.g. ``"0s (bounce)"``, ``"1-3m"``).
        limit: Maximum sessions to return in the paginated list
            (default 50).
        offset: Row offset for session pagination (default 0).
        filters: Optional list of column filters to narrow the dataset.
        entry_page: If set, further restrict to visits whose landing
            page matches this URL path.

    Returns:
        A dict containing:
        - ``sessions`` (list[dict]): Paginated visit details.
        - ``total`` (int): Total visits in this bucket (before pagination).
        - ``countries`` (list[dict]): Top 12 countries by visit count.
        - ``cities`` (list[dict]): Top 12 cities by visit count.
        - ``pages`` (list[dict]): Top 20 pages by view count.
        - ``entryPages`` (list[dict]): Top 12 landing pages with percentages.
        - ``journeys`` (list[dict]): Top 15 navigation paths.
        - ``sources`` (list[dict]): Top 12 referrer domains.
        - ``devices`` (list[dict]): Top 12 browser/device/OS combos.
        Returns an empty-data dict if ``bucket`` is not recognized.
    """
    filters = filters or []
    range_spec = BUCKET_RANGES.get(bucket)
    if range_spec is None:
        return {
            "sessions": [],
            "total": 0,
            "countries": [],
            "cities": [],
            "pages": [],
            "entryPages": [],
            "journeys": [],
            "sources": [],
            "devices": [],
        }

    filter_where, filter_params, session_join = prepare_filters(filters)

    # Build the SQL duration filter clause from the bucket's range spec.
    # Special case: the bounce bucket (0, 0) checks for exactly zero seconds.
    # Other buckets use a half-open interval [min, max).
    min_secs, max_secs = range_spec
    duration_filter = f"AND bv.duration_secs >= {min_secs}"
    if max_secs is not None:
        if min_secs == 0 and max_secs == 0:
            duration_filter += " AND bv.duration_secs = 0"
        else:
            duration_filter += f" AND bv.duration_secs < {max_secs}"

    entry_page_filter = ""
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
        **filter_params,
    }
    if entry_page:
        entry_page_filter = " AND ve.entry_page = {{entryPage}}"
        params["entryPage"] = entry_page

    # The base CTE is shared across all 9 concurrent sub-queries.
    # It defines the scope (time range, filters, duration bucket) once,
    # and each sub-query appends its own aggregation SELECT.
    # CTE chain: filtered_events -> visit_entries -> bucket_visits -> bucket_scope.
    #
    # Self-referrers (referrer_domain == hostname) are normalised to NULL
    # here so the downstream ``entry_referrer`` derivation collapses them
    # into the '(direct)' bucket -- internal navigation should not appear
    # as a distinct entry source in the sessions explorer.
    base_cte = f"""WITH filtered_events AS (
      SELECT
        we.visit_id,
        we.session_id,
        we.url_path,
        CASE
          WHEN REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')
               = COALESCE(REGEXP_REPLACE(we.hostname, '^www\\.', ''), '')
          THEN NULL
          ELSE REGEXP_REPLACE(we.referrer_domain, '^www\\.', '')
        END AS referrer_domain,
        we.created_at
      FROM website_event we
      {session_join}
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    ),
    visit_entries AS (
      SELECT DISTINCT ON (fe.visit_id)
        fe.visit_id,
        COALESCE(fe.url_path, '(unknown)') AS entry_page,
        COALESCE(NULLIF(fe.referrer_domain, ''), '(direct)') AS entry_referrer
      FROM filtered_events fe
      ORDER BY fe.visit_id, fe.created_at ASC
    ),
    bucket_visits AS (
      SELECT
        fe.visit_id,
        fe.session_id,
        COUNT(*)::bigint AS pages_viewed,
        EXTRACT(EPOCH FROM (MAX(fe.created_at) - MIN(fe.created_at))) AS duration_secs,
        MIN(fe.created_at) AS started_at
      FROM filtered_events fe
      GROUP BY fe.visit_id, fe.session_id
    ),
    bucket_scope AS (
      SELECT
        bv.visit_id,
        bv.session_id,
        bv.pages_viewed,
        bv.duration_secs,
        bv.started_at,
        ve.entry_page,
        ve.entry_referrer
      FROM bucket_visits bv
      JOIN visit_entries ve ON ve.visit_id = bv.visit_id
      WHERE 1=1
        {duration_filter}
        {entry_page_filter}
    )"""

    def _q(sql: str) -> list[dict[str, Any]]:
        """Execute an aggregation query against the shared base CTE.

        Prepends the ``base_cte`` (which defines filtered_events,
        visit_entries, bucket_visits, and bucket_scope) to the given
        SQL fragment and runs the combined query on the reused Django
        connection.

        Args:
            sql: A SQL SELECT statement that references CTEs from
                ``base_cte`` (typically ``bucket_scope bs``).

        Returns:
            List of row dicts from the query result.
        """
        return raw_query(f"{base_cte}\n{sql}", params)

    # Run the 9 sub-queries sequentially on the reused connection.  Each
    # reuses the base CTE and adds a specific aggregation.  (A previous
    # ThreadPoolExecutor variant was slower: a fresh TLS connection per
    # worker plus query serialisation on the remote Postgres.)
    count_rows = _q("SELECT COUNT(*)::bigint AS total FROM bucket_scope bs")
    session_rows = _q(
        f"""SELECT
      bs.visit_id, bs.session_id,
      COALESCE(s.country, '(not set)') AS country,
      COALESCE(s.city, '(not set)') AS city,
      COALESCE(s.browser, 'Unknown') AS browser,
      COALESCE(s.os, 'Unknown') AS os,
      COALESCE(s.device, 'Unknown') AS device,
      bs.entry_page AS landing_page, bs.pages_viewed, bs.duration_secs, bs.started_at
    FROM bucket_scope bs
    JOIN session s ON s.session_id = bs.session_id
    ORDER BY bs.started_at DESC
    LIMIT {limit} OFFSET {offset}"""
    )
    country_rows = _q(
        """SELECT COALESCE(s.country, '(not set)') AS country, COUNT(*)::bigint AS visits
    FROM bucket_scope bs JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1 ORDER BY visits DESC, country ASC LIMIT 12"""
    )
    city_rows = _q(
        """SELECT COALESCE(s.country, '(not set)') AS country,
      COALESCE(s.city, '(not set)') AS city, COUNT(*)::bigint AS visits
    FROM bucket_scope bs JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1, 2 ORDER BY visits DESC, country ASC, city ASC LIMIT 12"""
    )
    page_rows = _q(
        """SELECT fe.url_path, COUNT(*)::bigint AS views,
      COUNT(DISTINCT fe.visit_id)::bigint AS visits
    FROM filtered_events fe JOIN bucket_scope bs ON bs.visit_id = fe.visit_id
    GROUP BY fe.url_path ORDER BY views DESC, visits DESC, fe.url_path ASC LIMIT 20"""
    )
    entry_page_rows = _q(
        """SELECT bs.entry_page, COUNT(*)::bigint AS visits
    FROM bucket_scope bs GROUP BY 1 ORDER BY visits DESC, entry_page ASC LIMIT 12"""
    )
    # The journey query extends the base CTE with extra CTEs, so it builds
    # the full SQL itself rather than going through _q().
    journey_rows = raw_query(
        f"""{base_cte},
    visit_pages AS (
      SELECT fe.visit_id, fe.url_path,
        ROW_NUMBER() OVER (PARTITION BY fe.visit_id ORDER BY fe.created_at) AS rn
      FROM filtered_events fe
      JOIN bucket_scope bs ON bs.visit_id = fe.visit_id
    ),
    visit_journeys AS (
      SELECT visit_id, array_agg(url_path ORDER BY rn) AS journey
      FROM visit_pages WHERE rn <= 4 GROUP BY visit_id HAVING COUNT(*) >= 2
    )
    SELECT journey, COUNT(*)::bigint AS count
    FROM visit_journeys GROUP BY journey ORDER BY count DESC LIMIT 15""",
        params,
    )
    source_rows = _q(
        """SELECT bs.entry_referrer AS referrer_domain, COUNT(*)::bigint AS visits
    FROM bucket_scope bs GROUP BY 1 ORDER BY visits DESC, referrer_domain ASC LIMIT 12"""
    )
    device_rows = _q(
        """SELECT COALESCE(s.browser, 'Unknown') AS browser,
      COALESCE(s.device, 'Unknown') AS device,
      COALESCE(s.os, 'Unknown') AS os, COUNT(*)::bigint AS visits
    FROM bucket_scope bs JOIN session s ON s.session_id = bs.session_id
    GROUP BY 1, 2, 3 ORDER BY visits DESC, browser ASC, device ASC, os ASC LIMIT 12"""
    )

    total = int(count_rows[0]["total"] or 0) if count_rows else 0

    sessions = [
        {
            "visitId": row["visit_id"],
            "sessionId": row["session_id"],
            "country": row["country"],
            "city": row["city"],
            "browser": row["browser"],
            "os": row["os"],
            "device": row["device"],
            "landingPage": row["landing_page"],
            "pagesViewed": int(row["pages_viewed"] or 0),
            "durationSecs": round(float(row["duration_secs"] or 0), 1),
            "startedAt": row["started_at"].isoformat()
            if hasattr(row["started_at"], "isoformat")
            else str(row["started_at"]),
        }
        for row in session_rows
    ]

    countries = [
        {
            "country": row["country"],
            "visits": int(row["visits"] or 0),
        }
        for row in country_rows
    ]
    cities = [
        {
            "country": row["country"],
            "city": row["city"],
            "visits": int(row["visits"] or 0),
        }
        for row in city_rows
    ]
    pages = [
        {
            "urlPath": row["url_path"],
            "views": int(row["views"] or 0),
            "visits": int(row["visits"] or 0),
        }
        for row in page_rows
    ]
    entry_pages = [
        {
            "urlPath": row["entry_page"],
            "visits": int(row["visits"] or 0),
            "percentage": (int(row["visits"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in entry_page_rows
    ]
    journeys = [
        {
            "path": row["journey"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in journey_rows
    ]
    sources = [
        {
            "referrerDomain": row["referrer_domain"],
            "visits": int(row["visits"] or 0),
        }
        for row in source_rows
    ]
    devices = [
        {
            "browser": row["browser"],
            "device": row["device"],
            "os": row["os"],
            "visits": int(row["visits"] or 0),
        }
        for row in device_rows
    ]

    return {
        "sessions": sessions,
        "total": total,
        "countries": countries,
        "cities": cities,
        "pages": pages,
        "entryPages": entry_pages,
        "journeys": journeys,
        "sources": sources,
        "devices": devices,
    }
