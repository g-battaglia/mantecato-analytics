"""User journey paths — array_agg per visit with path length limit.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query


def get_journeys(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    path_length: int = 3,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find the most common page-level navigation paths across visits.

    Builds an ordered array of page URLs for each visit (truncated to
    ``path_length`` steps), then groups identical journeys and counts
    occurrences.  Used to power Sankey diagrams showing how visitors
    flow through the site.

    URL normalization strips query strings, fragment identifiers, and
    trailing slashes so that ``/blog/post/?ref=x#comments`` and
    ``/blog/post`` collapse into the same node.  Empty paths after
    stripping are mapped to ``/``.

    The query uses three CTEs:

    1. **visit_pages** -- assigns a row number to each pageview within
       a visit (ordered chronologically) and applies URL cleanup.
       Only the first ``path_length`` pages are kept (``rn <= N``).
    2. **deduped** -- removes consecutive duplicate pages using
       ``LAG()``, so a visitor who reloads the same page does not
       create a self-loop in the journey.
    3. **visit_journeys** -- aggregates the remaining pages into a
       PostgreSQL array via ``array_agg()``.  The ``HAVING COUNT(*) >= 2``
       clause excludes single-page visits (bounces), which are not
       meaningful journeys.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        path_length: Maximum number of steps to include per journey
            (default 3).  Higher values produce more granular but
            sparser journey data.
        limit: Maximum number of journey paths to return (default 20).

    Returns:
        List of dicts, each containing:
        - ``path`` (list[str]): Ordered list of URL paths in the journey.
        - ``count`` (int): Number of visits that followed this exact path.
        - ``percentage`` (float): This journey's share of total journeys
          returned (not of all site visits).
        Sorted by count descending.
    """
    # URL cleanup: strip query string (?...), fragment (#...), and trailing
    # slashes; coalesce empty result to '/' for the homepage.
    _strip = "REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(url_path, '?', 1), '#', 1), '/+$', '')"
    clean_url = f"CASE WHEN {_strip} = '' THEN '/' ELSE {_strip} END"

    rows = raw_query(
        f"""WITH visit_pages AS (
      SELECT
        visit_id,
        {clean_url} AS page,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at) AS rn
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND event_type = 1
    ),
    deduped AS (
      SELECT visit_id, page, rn,
             LAG(page) OVER (PARTITION BY visit_id ORDER BY rn) AS prev_page
      FROM visit_pages
      WHERE rn <= {path_length}
    ),
    visit_journeys AS (
      SELECT
        visit_id,
        array_agg(page ORDER BY rn) AS journey
      FROM deduped
      WHERE prev_page IS NULL OR page != prev_page
      GROUP BY visit_id
      HAVING COUNT(*) >= 2
    )
    SELECT
      journey,
      COUNT(*)::bigint AS count
    FROM visit_journeys
    GROUP BY journey
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    total = sum(int(r["count"] or 0) for r in rows)

    return [
        {
            "path": row["journey"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


def get_section_journeys(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    path_length: int = 3,
    limit: int = 20,
    depth: int = 2,
) -> list[dict[str, Any]]:
    """Find the most common section-level navigation paths across visits.

    Similar to ``get_journeys`` but groups pages into site *sections*
    based on URL path segments, reducing cardinality for sites with
    many unique pages.  For example, with ``depth=2``, the pages
    ``/blog/post-1`` and ``/blog/post-2`` both map to the section
    ``/blog``.

    The ``depth`` parameter controls how many leading path segments
    define a section.  ``depth=1`` uses only the first segment (e.g.
    ``/blog``), ``depth=2`` uses the first two (e.g. ``/blog/2024``).

    The section is extracted by splitting the URL on ``/`` and taking
    the first ``depth + 1`` array elements (element 0 is the empty
    string before the leading slash), then joining them back with ``/``.

    Unlike ``get_journeys``, consecutive duplicate *sections* are NOT
    deduplicated, since navigating between pages within the same
    section is a meaningful signal at the section level.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        path_length: Maximum number of section steps per journey
            (default 3).
        limit: Maximum number of journey paths to return (default 20).
        depth: Number of leading URL path segments that define a
            section (default 2).

    Returns:
        List of dicts, each containing:
        - ``path`` (list[str]): Ordered list of section identifiers.
        - ``count`` (int): Number of visits that followed this path.
        - ``percentage`` (float): This journey's share of total
          journeys returned.
        Sorted by count descending.
    """
    # slice_end = depth + 1 because PostgreSQL array slices are 1-based
    # and element [1] is the empty string before the leading '/'.
    slice_end = depth + 1
    clean_url = "REGEXP_REPLACE(SPLIT_PART(url_path, '?', 1), '/+$', '')"
    # Extract the first `depth` meaningful path segments by splitting on '/',
    # slicing the array, and re-joining.  COALESCE handles the root path
    # case where the result would be an empty string.
    section_expr = (
        f"COALESCE(NULLIF(array_to_string("
        f"(string_to_array({clean_url}, '/'))[1:{slice_end}], '/'), ''), '/')"
    )

    rows = raw_query(
        f"""WITH visit_pages AS (
      SELECT
        visit_id,
        {section_expr} AS section,
        ROW_NUMBER() OVER (PARTITION BY visit_id ORDER BY created_at) AS rn
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND event_type = 1
    ),
    visit_journeys AS (
      SELECT
        visit_id,
        array_agg(section ORDER BY rn) AS journey
      FROM visit_pages
      WHERE rn <= {path_length}
      GROUP BY visit_id
      HAVING COUNT(*) >= 2
    )
    SELECT
      journey,
      COUNT(*)::bigint AS count
    FROM visit_journeys
    GROUP BY journey
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    total = sum(int(r["count"] or 0) for r in rows)

    return [
        {
            "path": row["journey"],
            "count": int(row["count"] or 0),
            "percentage": (int(row["count"] or 0) / total) * 100 if total > 0 else 0,
        }
        for row in rows
    ]


def get_section_conversions(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    depth: int = 2,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Analyze cross-section navigation and event conversion per entry section.

    For each entry section (the first section a visitor lands in),
    computes:

    1. **Destinations** -- which other sections the visitor navigated
       to during the same session (cross-section flow).
    2. **Events** -- which custom events (``event_type = 2``) fired
       during sessions that entered through this section.

    This powers the "Conversion Flows" view, showing how entry points
    correlate with downstream engagement and conversions.

    The query uses five CTEs for efficient computation:

    1. **section_visits** -- maps each (session, section) pair to its
       first visit timestamp.
    2. **entry_section** -- uses ``DISTINCT ON`` to pick the earliest
       section per session as the "entry" section.
    3. **entry_totals** -- counts total sessions per entry section.
    4. **cross_sections** -- for each entry section, counts sessions
       that also visited a *different* section.
    5. **cross_events** -- for each entry section, counts custom events
       fired by those sessions.

    JSON aggregation (``json_agg`` + ``json_build_object``) is used in
    the final SELECT to nest destination and event breakdowns within
    each entry section row, avoiding N+1 queries.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        depth: Number of leading URL segments that define a section
            (default 2).
        limit: Maximum number of entry sections to return (default 5).

    Returns:
        List of dicts, each containing:
        - ``entry`` (str): The entry section path (e.g. ``"/blog"``).
        - ``totalSessions`` (int): Sessions that entered here.
        - ``destinations`` (list[dict]): Up to 10 sections visited
          after entry, each with ``section``, ``sessions``, and ``pct``.
        - ``events`` (list[dict]): Up to 10 events triggered, each
          with ``eventName``, ``count``, ``sessions``, and ``pct``.
        Sorted by totalSessions descending.
    """
    import json as _json

    slice_end = depth + 1
    clean_url = "REGEXP_REPLACE(SPLIT_PART(we.url_path, '?', 1), '/+$', '')"
    section_expr = (
        f"COALESCE(NULLIF(array_to_string("
        f"(string_to_array({clean_url}, '/'))[1:{slice_end}], '/'), ''), '/')"
    )

    rows = raw_query(
        f"""WITH section_visits AS MATERIALIZED (
      SELECT we.session_id, {section_expr} AS section, MIN(we.created_at) AS first_visit
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
      GROUP BY we.session_id, 2
    ),
    entry_section AS MATERIALIZED (
      SELECT DISTINCT ON (session_id) session_id, section AS entry
      FROM section_visits ORDER BY session_id, first_visit
    ),
    entry_totals AS (
      SELECT entry, COUNT(DISTINCT session_id)::bigint AS total
      FROM entry_section GROUP BY entry
    ),
    cross_sections AS (
      SELECT es.entry, sv.section AS dest,
        COUNT(DISTINCT sv.session_id)::bigint AS sessions
      FROM entry_section es
      JOIN section_visits sv ON es.session_id = sv.session_id AND es.entry != sv.section
      GROUP BY es.entry, sv.section
    ),
    cross_events AS (
      SELECT es.entry, we.event_name,
        COUNT(*)::bigint AS event_count,
        COUNT(DISTINCT we.session_id)::bigint AS sessions
      FROM entry_section es
      JOIN website_event we ON es.session_id = we.session_id
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.event_type = 2 AND we.event_name IS NOT NULL
      GROUP BY es.entry, we.event_name
    )
    SELECT et.entry, et.total,
      COALESCE((SELECT json_agg(json_build_object('section', cs.dest, 'sessions', cs.sessions)
                ORDER BY cs.sessions DESC)
                FROM cross_sections cs WHERE cs.entry = et.entry), '[]'::json) AS destinations,
      COALESCE((SELECT json_agg(json_build_object('eventName', ce.event_name,
                'count', ce.event_count, 'sessions', ce.sessions)
                ORDER BY ce.sessions DESC)
                FROM cross_events ce WHERE ce.entry = et.entry), '[]'::json) AS events
    FROM entry_totals et
    ORDER BY et.total DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    # Post-processing: the SQL returns JSON-aggregated arrays for destinations
    # and events.  Depending on the DB driver, these may arrive as Python
    # lists or as JSON strings, so we handle both cases.
    result = []
    for row in rows:
        total = int(row["total"] or 0)
        dests = (
            row["destinations"]
            if isinstance(row["destinations"], list)
            else _json.loads(row["destinations"] or "[]")
        )
        evts = (
            row["events"] if isinstance(row["events"], list) else _json.loads(row["events"] or "[]")
        )
        # Compute percentage of entry sessions that reached each destination
        # or triggered each event.
        for d in dests:
            d["pct"] = round(int(d["sessions"]) / total * 100, 1) if total else 0
        for e in evts:
            e["pct"] = round(int(e["sessions"]) / total * 100, 1) if total else 0
        # Cap at 10 destinations/events to keep the response payload
        # manageable for the frontend Sankey/flow visualization.
        result.append(
            {
                "entry": row["entry"],
                "totalSessions": total,
                "destinations": dests[:10],
                "events": evts[:10],
            }
        )
    return result
