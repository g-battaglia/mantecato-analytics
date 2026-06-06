"""Device dimension queries — browser, OS, device breakdowns for aggregate pageviews.

Privacy-first: aggregate pageview counts per device dimension. No visitor counts
(those require session tracking). Data comes directly from website_event columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, build_filter_sql

_MULTI_DIMENSIONS = ("browser", "os", "device")


def get_device_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    dimension: str,
    limit: int = 20,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate pageview counts by a device dimension.

    Dimensions are stored directly on ``website_event`` (no session join needed).

    Args:
        dimension: One of ``"browser"``, ``"os"``, ``"device"``.

    Returns:
        List of dicts with ``value``, ``pageviews``, ``percentage``, sorted
        by pageviews descending.
    """
    valid_dimensions = ["browser", "os", "device"]
    if dimension not in valid_dimensions:
        return []
    filters = filters or []

    rows = raw_query(
        f"""SELECT
      we.{dimension} AS value,
      COUNT(*)::bigint AS pageviews
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 1
      AND we.{dimension} IS NOT NULL
      AND we.{dimension} != ''
    GROUP BY we.{dimension}
    ORDER BY pageviews DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    total = sum(int(r["pageviews"] or 0) for r in rows)

    return [
        {
            "value": row["value"],
            "pageviews": int(row["pageviews"] or 0),
            "percentage": round((int(row["pageviews"] or 0) / total) * 100, 1) if total > 0 else 0,
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
    """Return browser / OS / device breakdowns in a single round trip.

    Uses a MATERIALIZED CTE to scan website_event once, then aggregates
    per dimension via UNION ALL with ROW_NUMBER() limiting.
    """
    filters = filters or []

    union_parts: list[str] = []
    for dim in _MULTI_DIMENSIONS:
        union_parts.append(
            f"""SELECT '{dim}' AS dim, {dim} AS value,
              COUNT(*)::bigint AS pageviews
            FROM base
            WHERE {dim} IS NOT NULL AND {dim} != ''
            GROUP BY {dim}"""
        )
    union_sql = "\n            UNION ALL\n            ".join(union_parts)

    rows = raw_query(
        f"""WITH base AS MATERIALIZED (
      SELECT we.browser, we.os, we.device
      FROM website_event we
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
        AND we.event_type = 1
    ),
    combined AS (
      {union_sql}
    ),
    ranked AS (
      SELECT dim, value, pageviews,
        ROW_NUMBER() OVER (PARTITION BY dim ORDER BY pageviews DESC) AS rn
      FROM combined
    )
    SELECT dim, value, pageviews
    FROM ranked
    WHERE rn <= {limit}
    ORDER BY dim, pageviews DESC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    out: dict[str, list[dict[str, Any]]] = {dim: [] for dim in _MULTI_DIMENSIONS}
    totals: dict[str, int] = {dim: 0 for dim in _MULTI_DIMENSIONS}
    for row in rows:
        totals[row["dim"]] += int(row["pageviews"] or 0)
    for row in rows:
        dim = row["dim"]
        pageviews = int(row["pageviews"] or 0)
        out[dim].append(
            {
                "value": row["value"],
                "pageviews": pageviews,
                "percentage": round((pageviews / totals[dim]) * 100, 1) if totals[dim] > 0 else 0,
            }
        )
    return out
