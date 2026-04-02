"""
Revenue queries — summary, time series, by event, and by country.
Ported verbatim from src/queries/revenue.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query


async def get_revenue_summary(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    rows = await raw_query(
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


async def get_revenue_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
) -> list[dict[str, Any]]:
    valid_granularities = ["hour", "day", "week", "month"]
    gran = granularity if granularity in valid_granularities else "day"

    rows = await raw_query(
        f"""SELECT
      date_trunc('{gran}', r.created_at) AS time,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    WHERE r.website_id = {{{{websiteId::uuid}}}}
      AND r.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
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


async def get_revenue_by_event(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""SELECT
      r.event_name,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions,
      COALESCE(AVG(r.revenue), 0) AS avg_revenue
    FROM revenue r
    WHERE r.website_id = {{{{websiteId::uuid}}}}
      AND r.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
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


async def get_revenue_by_country(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = await raw_query(
        f"""SELECT
      s.country,
      COALESCE(SUM(r.revenue), 0) AS revenue,
      COUNT(*)::bigint AS transactions
    FROM revenue r
    JOIN session s ON s.session_id = r.session_id
    WHERE r.website_id = {{{{websiteId::uuid}}}}
      AND r.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
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
