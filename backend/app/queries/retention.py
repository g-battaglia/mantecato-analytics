"""
Cohort retention analysis using generate_series.
Ported verbatim from src/queries/retention.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..database import raw_query


async def get_retention(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str = "week",
) -> list[dict[str, Any]]:
    if granularity not in ("week", "month"):
        granularity = "week"

    rows = await raw_query(
        f"""WITH first_visit AS (
      SELECT
        session_id,
        date_trunc('{granularity}', MIN(created_at)) AS cohort
      FROM website_event
      WHERE website_id = {{{{websiteId::uuid}}}}
        AND created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND event_type = 1
      GROUP BY session_id
    ),
    cohort_sizes AS (
      SELECT cohort, COUNT(DISTINCT session_id) AS cohort_size
      FROM first_visit
      GROUP BY cohort
    ),
    return_visits AS (
      SELECT
        fv.cohort,
        fv.session_id,
        EXTRACT(EPOCH FROM (date_trunc('{granularity}', we.created_at) - fv.cohort))
          / EXTRACT(EPOCH FROM INTERVAL '1 {granularity}') AS period
      FROM website_event we
      JOIN first_visit fv ON we.session_id = fv.session_id
      WHERE we.website_id = {{{{websiteId::uuid}}}}
        AND we.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
        AND we.event_type = 1
    )
    SELECT
      cs.cohort,
      cs.cohort_size,
      rv.period::int AS period,
      COUNT(DISTINCT rv.session_id)::bigint AS retained
    FROM cohort_sizes cs
    CROSS JOIN generate_series(0, 12) AS rv_period(p)
    LEFT JOIN return_visits rv ON rv.cohort = cs.cohort AND rv.period = rv_period.p
    WHERE rv_period.p >= 0
    GROUP BY cs.cohort, cs.cohort_size, rv.period
    ORDER BY cs.cohort, rv.period""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
        },
    )

    # Group rows by cohort into RetentionCohort objects
    cohort_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        cohort_key = (
            row["cohort"].isoformat()
            if isinstance(row["cohort"], datetime)
            else str(row["cohort"])
        )
        if cohort_key not in cohort_map:
            cohort_map[cohort_key] = {
                "cohortSize": int(row["cohort_size"] or 0),
                "periods": {},
            }
        if row.get("period") is not None:
            cohort_map[cohort_key]["periods"][int(row["period"])] = int(
                row["retained"] or 0
            )

    max_periods = 12
    result: list[dict[str, Any]] = []
    for cohort_key, data in cohort_map.items():
        periods: list[float] = []
        for i in range(max_periods + 1):
            retained = data["periods"].get(i, 0)
            periods.append(
                (retained / data["cohortSize"]) * 100 if data["cohortSize"] > 0 else 0
            )
        result.append(
            {
                "cohort": cohort_key,
                "cohortSize": data["cohortSize"],
                "periods": periods,
            }
        )

    return result
