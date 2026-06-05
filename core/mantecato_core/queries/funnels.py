"""Funnel analysis with dynamic CTE chains.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.mantecato_core.database import raw_query


def get_funnel(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    steps: list[dict[str, str]],
    window_minutes: int = 60,
) -> list[dict[str, Any]]:
    """Run funnel analysis with a sequence of URL/event steps."""
    if len(steps) < 2:
        return []

    ctes: list[str] = []
    params: dict[str, Any] = {
        "websiteId": website_id,
        "startDate": start_date,
        "endDate": end_date,
    }

    s0 = steps[0]
    if s0["type"] == "url":
        s0_condition = "we.url_path = {{step0Val}} AND we.event_type = 1"
    else:
        s0_condition = "we.event_name = {{step0Val}} AND we.event_type = 2"
    params["step0Val"] = s0["value"]

    ctes.append(
        f"""step0 AS (
    SELECT DISTINCT we.session_id, MIN(we.created_at) AS step_time
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND {s0_condition}
    GROUP BY we.session_id
  )"""
    )

    for i in range(1, len(steps)):
        s = steps[i]
        if s["type"] == "url":
            condition = f"we.url_path = {{{{step{i}Val}}}} AND we.event_type = 1"
        else:
            condition = f"we.event_name = {{{{step{i}Val}}}} AND we.event_type = 2"
        params[f"step{i}Val"] = s["value"]

        ctes.append(
            f"""step{i} AS (
    SELECT DISTINCT we.session_id, MIN(we.created_at) AS step_time
    FROM website_event we
    JOIN step{i - 1} prev ON we.session_id = prev.session_id
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND {condition}
      AND we.created_at >= prev.step_time
      AND we.created_at <= prev.step_time + INTERVAL '{window_minutes} minutes'
    GROUP BY we.session_id
  )"""
        )

    selects = ", ".join(
        f"(SELECT COUNT(*) FROM step{i}) AS step{i}_count" for i in range(len(steps))
    )

    sql = f"WITH {', '.join(ctes)} SELECT {selects}"

    rows = raw_query(sql, params)
    row = rows[0] if rows else {}

    funnel_steps: list[dict[str, Any]] = []
    prev_visitors = 0

    for i, s in enumerate(steps):
        visitors = int(row.get(f"step{i}_count") or 0)
        dropoff = 0 if i == 0 else prev_visitors - visitors
        conversion_rate = (
            100.0 if i == 0 else ((visitors / prev_visitors) * 100 if prev_visitors > 0 else 0)
        )

        funnel_steps.append(
            {
                "step": i + 1,
                "label": s["value"],
                "visitors": visitors,
                "dropoff": dropoff,
                "conversionRate": conversion_rate,
            }
        )
        prev_visitors = visitors

    return funnel_steps
