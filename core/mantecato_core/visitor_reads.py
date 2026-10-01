"""SQL session aggregates for the dashboard, not API v1 metric semantics.

Return aggregate rows only: no event arrays, visitor sets or large IN lists in
Python. Keep the dashboard's per-gap integer duration (API v1 uses float seconds).
"""

from __future__ import annotations

from django.core.exceptions import EmptyResultSet
from django.db import connection


def _session_sql(qs, *, landing=False, integer_gap=False):
    fields = ["event_id", "visitor_key", "created_at"]
    if landing:
        fields.append("url_path")
    source, params = qs.order_by().values(*fields).query.sql_with_params()
    # Legacy totals/landings truncate each gap BEFORE comparing; bucket reads
    # compare timestamps directly. Preserve both rather than changing metrics.
    gap = "EXTRACT(EPOCH FROM created_at - previous_at)"
    if integer_gap:
        gap = f"FLOOR({gap})"
    return (
        f"""WITH source AS ({source}),
      marked AS (
        SELECT *, LAG(created_at) OVER (
          PARTITION BY visitor_key ORDER BY created_at, event_id
        ) AS previous_at FROM source
      ), numbered AS (
        SELECT *, SUM(CASE WHEN previous_at IS NULL OR
          {gap} > 1800 THEN 1 ELSE 0 END)
          OVER (PARTITION BY visitor_key ORDER BY created_at, event_id
                ROWS UNBOUNDED PRECEDING) AS session_no FROM marked
      ), sessions AS (
        SELECT visitor_key, session_no, MIN(created_at) AS session_start,
          COUNT(*) AS pageviews,
          SUM(CASE WHEN previous_at IS NOT NULL AND
            {gap} <= 1800
            THEN FLOOR(EXTRACT(EPOCH FROM created_at - previous_at)) ELSE 0 END) AS duration
        FROM numbered GROUP BY visitor_key, session_no
      )""",
        params,
    )


def _fetch(qs, suffix, *, landing=False, integer_gap=False):
    try:
        sql, params = _session_sql(qs, landing=landing, integer_gap=integer_gap)
    except EmptyResultSet:
        return []
    with connection.cursor() as cursor:
        cursor.execute(sql + suffix, params)
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def session_totals(qs):
    rows = _fetch(
        qs,
        """SELECT
      COUNT(DISTINCT visitor_key) +
        CASE WHEN COUNT(*) FILTER (WHERE visitor_key IS NULL) > 0 THEN 1 ELSE 0 END
        AS unique_visitors,
      COUNT(*) AS visits, COUNT(*) FILTER (WHERE pageviews = 1) AS bounces,
      COALESCE(SUM(pageviews), 0) AS total_pageviews,
      COALESCE(SUM(duration), 0) AS total_duration_s FROM sessions""",
        integer_gap=True,
    )
    keys = ("unique_visitors", "visits", "bounces", "total_pageviews", "total_duration_s")
    return {key: int(rows[0][key] or 0) if rows else 0 for key in keys}


def session_landings(qs):
    rows = _fetch(
        qs,
        """, entries AS (
      SELECT DISTINCT ON (visitor_key, session_no) visitor_key, session_no, url_path
      FROM numbered ORDER BY visitor_key, session_no, created_at, event_id
    ) SELECT COALESCE(NULLIF(e.url_path, ''), '/') AS entry_path,
      COUNT(*) AS visits, COUNT(*) FILTER (WHERE s.pageviews = 1) AS bounces
      FROM entries e JOIN sessions s ON e.visitor_key IS NOT DISTINCT FROM s.visitor_key
        AND e.session_no = s.session_no
      GROUP BY COALESCE(NULLIF(e.url_path, ''), '/')""",
        landing=True,
        integer_gap=True,
    )
    return {
        row["entry_path"]: {"visits": int(row["visits"]), "bounces": int(row["bounces"])}
        for row in rows
    }


def session_buckets(qs, granularity):
    if granularity not in ("minute", "hour", "day", "week", "month"):
        granularity = "day"
    rows = _fetch(
        qs,
        f"""SELECT
      date_trunc('{granularity}', session_start AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        AS bucket, COUNT(*) AS visits FROM sessions GROUP BY 1""",
    )
    return {row["bucket"].isoformat(): int(row["visits"]) for row in rows}
