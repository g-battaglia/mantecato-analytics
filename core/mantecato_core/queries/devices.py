"""Device dimension queries — browser, OS, device, screen, language breakdowns.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, build_filter_sql

# Dimensions exposed by :func:`get_device_metrics_multi`.  Validated against
# this list because the names are interpolated into the SQL string (the
# placeholder substitution layer only handles values, not identifiers).
_MULTI_DIMENSIONS = ("browser", "os", "device", "language")


def get_device_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    dimension: str,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate visitor and pageview counts by a device/environment dimension.

    Supports five dimensions stored on the ``session`` table:

    - ``"browser"`` -- e.g. Chrome, Firefox, Safari.
    - ``"os"`` -- e.g. Windows, macOS, Android.
    - ``"device"`` -- e.g. desktop, mobile, tablet.
    - ``"screen"`` -- screen resolution string (e.g. ``"1920x1080"``).
    - ``"language"`` -- browser language code (e.g. ``"en-US"``).

    The dimension column is interpolated directly into the SQL string,
    so it is validated against a strict whitelist to prevent injection.

    A JOIN to the ``session`` table is always required since all five
    dimensions are session-level attributes (parsed from the User-Agent
    and Accept-Language headers during event ingestion).

    Each result row includes a ``percentage`` field computed in Python
    as the fraction of total visitors, useful for rendering pie charts.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        dimension: Which device column to group by.  Must be one of
            ``"browser"``, ``"os"``, ``"device"``, ``"screen"``, or
            ``"language"``.
        limit: Maximum number of rows to return (default 20).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``value`` (str): The dimension value.
        - ``visitors`` (int): Unique session count.
        - ``pageviews`` (int): Total pageview count.
        - ``percentage`` (float): This value's share of total visitors.
        Sorted by visitors descending.  Returns empty list if
        ``dimension`` is not in the allowed set.
    """
    # Whitelist check prevents SQL injection since dimension is interpolated
    # directly into the SQL string (in both SELECT and WHERE clauses).
    valid_dimensions = ["browser", "os", "device", "screen", "language"]
    if dimension not in valid_dimensions:
        return []
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    rows = raw_query(
        f"""SELECT
      s.{dimension} AS value,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    JOIN session s ON s.session_id = we.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND s.{dimension} IS NOT NULL
      AND s.{dimension} != ''
      {filter_where}
    GROUP BY s.{dimension}
    ORDER BY visitors DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    # Compute total visitors across all returned rows so we can derive
    # per-value percentages in Python (simpler than a window function).
    total = sum(int(r["visitors"] or 0) for r in rows)

    return [
        {
            "value": row["value"],
            "visitors": int(row["visitors"] or 0),
            "pageviews": int(row["pageviews"] or 0),
            "percentage": round((int(row["visitors"] or 0) / total) * 100, 1) if total > 0 else 0,
        }
        for row in rows
    ]


def get_device_metrics_multi(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10,
    filters: list[Filter] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return browser / OS / device / language breakdowns in a single round trip.

    The analytics overview originally invoked :func:`get_device_metrics` four
    times (one per dimension), paying four full network round trips and four
    independent scans of ``website_event``.  This consolidated variant
    issues one SQL statement that scans the data once, splits it into four
    aggregations via ``UNION ALL``, and applies a per-dimension ``LIMIT``
    using ``ROW_NUMBER()``.

    The base CTE is declared ``AS MATERIALIZED`` so PostgreSQL 12+ does not
    re-inline (and re-execute) the scan for each branch of the union.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive lower bound of the analysis window (UTC).
        end_date: Inclusive upper bound of the analysis window (UTC).
        limit: Maximum number of rows kept *per dimension* (default 10).
        filters: Optional list of column filters applied to the base scan.

    Returns:
        A dict with one entry per dimension (``browser``, ``os``,
        ``device``, ``language``).  Each value is the same shape returned
        by :func:`get_device_metrics`: a list of dicts with ``value``,
        ``visitors``, ``pageviews``, and ``percentage`` keys, sorted by
        visitors descending.

    Notes:
        The ``screen`` dimension is intentionally excluded because the
        overview page does not display it; callers that need a screen
        breakdown should continue to use :func:`get_device_metrics`.
    """
    filters = filters or []
    result = build_filter_sql(filters)
    filter_where = result["where"]
    filter_params = result["params"]

    # One MATERIALIZED CTE pulls the joined event+session rows exactly once;
    # the per-dimension aggregations downstream read from this in-memory
    # tuplestore instead of re-running the join.
    union_parts: list[str] = []
    for dim in _MULTI_DIMENSIONS:
        union_parts.append(
            f"""SELECT '{dim}' AS dim, {dim} AS value,
              COUNT(DISTINCT session_id)::bigint AS visitors,
              COUNT(*)::bigint AS pageviews
            FROM base
            WHERE {dim} IS NOT NULL AND {dim} != ''
            GROUP BY {dim}"""
        )
    union_sql = "\n            UNION ALL\n            ".join(union_parts)

    rows = raw_query(
        f"""WITH base AS MATERIALIZED (
      SELECT s.browser, s.os, s.device, s.language, we.session_id
      FROM website_event we
      JOIN session s ON s.session_id = we.session_id
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
        {filter_where}
    ),
    combined AS (
      {union_sql}
    ),
    ranked AS (
      SELECT dim, value, visitors, pageviews,
        ROW_NUMBER() OVER (PARTITION BY dim ORDER BY visitors DESC) AS rn
      FROM combined
    )
    SELECT dim, value, visitors, pageviews
    FROM ranked
    WHERE rn <= {limit}
    ORDER BY dim, visitors DESC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            **filter_params,
        },
    )

    # Bucket the rows by dimension and pre-compute per-dimension totals so
    # the percentage field matches the single-dimension helper exactly.
    out: dict[str, list[dict[str, Any]]] = {dim: [] for dim in _MULTI_DIMENSIONS}
    totals: dict[str, int] = {dim: 0 for dim in _MULTI_DIMENSIONS}
    for row in rows:
        totals[row["dim"]] += int(row["visitors"] or 0)
    for row in rows:
        dim = row["dim"]
        visitors = int(row["visitors"] or 0)
        out[dim].append(
            {
                "value": row["value"],
                "visitors": visitors,
                "pageviews": int(row["pageviews"] or 0),
                "percentage": round((visitors / totals[dim]) * 100, 1) if totals[dim] > 0 else 0,
            }
        )
    return out
