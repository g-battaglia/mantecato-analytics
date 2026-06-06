"""Revenue queries — summary, time series, by event, and by country.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query


def get_revenue_summary(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """Compute aggregate revenue metrics for the given time period.

    Queries the ``revenue`` table (populated by the tracker when events
    carry a revenue amount) to produce headline KPIs: total revenue,
    transaction count, unique customers, and average revenue per user
    (ARPU).

    ARPU is computed in Python (not SQL) to avoid a division-by-zero
    when there are no customers in the period.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.

    Returns:
        A single dict containing:
        - ``totalRevenue`` (float): Sum of all revenue in the period.
        - ``transactions`` (int): Total number of revenue events.
        - ``uniqueCustomers`` (int): Distinct session count with revenue.
        - ``arpu`` (float): Average revenue per unique customer, or 0
          if no customers exist in the period.
    """
    rows = raw_query(
        """SELECT
      COALESCE(SUM(r.revenue), 0) AS total_revenue,
      COUNT(*)::bigint AS transactions,
      COUNT(DISTINCT r.session_id)::bigint AS unique_customers
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}""",
        {"websiteId": website_id, "startDate": start_date, "endDate": end_date},
    )

    row = rows[0] if rows else {}
    total_revenue = float(row.get("total_revenue") or 0)
    unique_customers = int(row.get("unique_customers") or 0)

    return {
        "totalRevenue": total_revenue,
        "transactions": int(row.get("transactions") or 0),
        "uniqueCustomers": unique_customers,
        "arpu": total_revenue / unique_customers if unique_customers > 0 else 0,
    }


def get_revenue_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
) -> list[dict[str, Any]]:
    """Generate a time series of revenue and transaction counts.

    Uses ``date_trunc()`` to bucket revenue events into time intervals.
    Only intervals containing at least one transaction are included;
    the frontend fills gaps with zero-value data points when rendering
    the chart.

    The ``granularity`` parameter is validated against a whitelist
    (excluding ``"minute"`` since revenue data is typically too sparse
    for minute-level granularity) and defaults to ``"day"`` if invalid.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        granularity: Time bucket size -- one of ``"hour"``, ``"day"``,
            ``"week"``, or ``"month"``.  Defaults to ``"day"`` if invalid.

    Returns:
        List of dicts ordered chronologically, each containing:
        - ``time`` (str): ISO 8601 timestamp of the bucket start.
        - ``revenue`` (float): Total revenue in this bucket.
        - ``transactions`` (int): Number of revenue events in this bucket.
    """
    # Whitelist validation: granularity is interpolated into the SQL string.
    # "minute" is intentionally excluded -- revenue events are too sparse.
    valid_granularities = ["hour", "day", "week", "month"]
    gran = granularity if granularity in valid_granularities else "day"

    rows = raw_query(
        f"""SELECT
      date_trunc('{gran}', r.created_at) AS time,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
    GROUP BY 1
    ORDER BY 1 ASC""",
        {"websiteId": website_id, "startDate": start_date, "endDate": end_date},
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "revenue": float(row["revenue"] or 0),
            "transactions": int(row["transactions"] or 0),
        }
        for row in rows
    ]


def get_revenue_by_event(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Break down revenue metrics by the event name that generated them.

    Each revenue record in the ``revenue`` table is associated with an
    event name (e.g. ``"purchase"``, ``"subscription"``).  This query
    aggregates total revenue, transaction count, and average transaction
    value per event name, helping identify which conversion events
    drive the most revenue.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of event rows to return (default 20).

    Returns:
        List of dicts, each containing:
        - ``eventName`` (str): The revenue event name.
        - ``revenue`` (float): Total revenue from this event.
        - ``transactions`` (int): Number of transactions.
        - ``avgRevenue`` (float): Average revenue per transaction.
        Sorted by revenue descending.
    """
    rows = raw_query(
        f"""SELECT
      r.event_name,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions,
      COALESCE(AVG(r.revenue), 0) AS avg_revenue
    FROM revenue r
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
    GROUP BY r.event_name
    ORDER BY revenue DESC
    LIMIT {limit}""",
        {"websiteId": website_id, "startDate": start_date, "endDate": end_date},
    )

    return [
        {
            "eventName": row["event_name"],
            "revenue": float(row["revenue"] or 0),
            "transactions": int(row["transactions"] or 0),
            "avgRevenue": float(row["avg_revenue"] or 0),
        }
        for row in rows
    ]


def get_revenue_by_country(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Break down revenue metrics by the visitor's country.

    Joins the ``revenue`` table to ``session`` to obtain the country
    code (derived from IP geolocation during ingestion).  Sessions
    without a country (NULL) are excluded from the results.

    This query requires the JOIN to ``session`` because geographic data
    is stored on the session row, not on the revenue row itself.

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of country rows to return (default 20).

    Returns:
        List of dicts, each containing:
        - ``country`` (str): ISO 3166-1 alpha-2 country code.
        - ``revenue`` (float): Total revenue from this country.
        - ``transactions`` (int): Number of transactions.
        Sorted by revenue descending.
    """
    rows = raw_query(
        f"""SELECT
      s.country,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    JOIN session s ON s.session_id = r.session_id
    WHERE r.website_id = {{websiteId::uuid}}
      AND r.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND s.country IS NOT NULL
    GROUP BY s.country
    ORDER BY revenue DESC
    LIMIT {limit}""",
        {"websiteId": website_id, "startDate": start_date, "endDate": end_date},
    )

    return [
        {
            "country": row["country"],
            "revenue": float(row["revenue"] or 0),
            "transactions": int(row["transactions"] or 0),
        }
        for row in rows
    ]
