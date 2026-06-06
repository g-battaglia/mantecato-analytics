"""Cohort retention analysis using generate_series.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query


def get_retention(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str = "week",
) -> list[dict[str, Any]]:
    """Compute a cohort retention matrix showing return-visit rates over time.

    Groups visitors into cohorts based on when they first visited the
    site (truncated to the specified granularity), then measures what
    fraction of each cohort returned in subsequent periods.

    The query uses three CTEs:

    1. **first_visit** -- determines each session's cohort by
       ``date_trunc``-ing its earliest event timestamp.
    2. **cohort_sizes** -- counts distinct sessions per cohort.
    3. **return_visits** -- for each session, computes which period
       (0, 1, 2, ...) relative to their cohort each subsequent visit
       falls in.  Period 0 is the cohort's own period; period 1 is
       the next week/month, etc.

    A ``CROSS JOIN generate_series(0, 12)`` ensures all 13 periods
    (0 through 12) appear for every cohort even if no one returned,
    so the retention grid is always rectangular.

    The period offset is computed by dividing the epoch-second
    difference between the visit's truncated timestamp and the cohort
    timestamp by the number of seconds in one granularity interval
    (``INTERVAL '1 week'`` or ``INTERVAL '1 month'``).

    Post-processing in Python converts raw retained counts into
    percentages (retained / cohort_size * 100).

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        granularity: Cohort period size -- ``"week"`` or ``"month"``
            (default ``"week"``).

    Returns:
        List of dicts, one per cohort, each containing:
        - ``cohort`` (str): ISO 8601 timestamp of the cohort start.
        - ``cohortSize`` (int): Number of unique sessions in the cohort.
        - ``periods`` (list[float]): 13 retention percentages (period 0
          through period 12).  Period 0 is always 100% by definition.
        Ordered by cohort ascending.
    """
    # Only week and month are supported; finer granularities produce
    # too many cohorts and coarser ones are not meaningful.
    if granularity not in ("week", "month"):
        granularity = "week"

    rows = raw_query(
        f"""WITH first_visit AS (
      SELECT
        session_id,
        date_trunc('{granularity}', MIN(created_at)) AS cohort
      FROM website_event
      WHERE website_id = {{websiteId::uuid}}
        AND created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
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
      WHERE we.website_id = {{websiteId::uuid}}
        AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
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

    # Build a cohort map keyed by ISO timestamp, accumulating retained
    # counts per period.  The SQL may return NULL periods for cohort/period
    # combos with no return visits (due to the CROSS JOIN + LEFT JOIN).
    cohort_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        cohort_key = (
            row["cohort"].isoformat() if isinstance(row["cohort"], datetime) else str(row["cohort"])
        )
        if cohort_key not in cohort_map:
            cohort_map[cohort_key] = {
                "cohortSize": int(row["cohort_size"] or 0),
                "periods": {},
            }
        if row.get("period") is not None:
            cohort_map[cohort_key]["periods"][int(row["period"])] = int(row["retained"] or 0)

    # Convert raw retained counts to percentages for each of the 13 periods.
    # Missing periods default to 0 (no one returned).
    max_periods = 12
    result: list[dict[str, Any]] = []
    for cohort_key, data in cohort_map.items():
        periods: list[float] = []
        for i in range(max_periods + 1):
            retained = data["periods"].get(i, 0)
            periods.append((retained / data["cohortSize"]) * 100 if data["cohortSize"] > 0 else 0)
        result.append(
            {
                "cohort": cohort_key,
                "cohortSize": data["cohortSize"],
                "periods": periods,
            }
        )

    return result
