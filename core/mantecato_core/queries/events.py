"""Custom-event aggregate queries.

Privacy-first: custom events are counted by name only. No event payload,
properties, visitor profile, or session path is stored or queried.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import Filter, GRANULARITIES, prepare_filters, safe_identifier
from core.mantecato_core.queries.orm_fallbacks import (
    custom_event_queryset,
    event_metric_rows,
    truncate_dt,
    should_use_orm_fallback,
)


def get_event_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return aggregate custom-event counts by event name."""
    if should_use_orm_fallback():
        return event_metric_rows(
            custom_event_queryset(website_id, start_date, end_date, filters),
            limit,
        )

    filter_where, filter_params, _ = prepare_filters(filters or [])
    rows = raw_query(
        f"""SELECT
      we.event_name AS event_name,
      COUNT(*)::bigint AS count,
      MAX(we.created_at) AS last_triggered
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name IS NOT NULL
      AND we.event_name != ''
      {filter_where}
    GROUP BY we.event_name
    ORDER BY count DESC
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
            "eventName": row["event_name"],
            "count": int(row["count"] or 0),
            "lastTriggered": row["last_triggered"].isoformat()
            if isinstance(row["last_triggered"], datetime)
            else str(row["last_triggered"] or ""),
        }
        for row in rows
    ]


def get_event_time_series(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    event_names: list[str],
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Return time series for selected event names."""
    if not event_names:
        return []
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    if should_use_orm_fallback():
        grouped: dict[str, dict[datetime, int]] = {name: {} for name in event_names}
        qs = custom_event_queryset(website_id, start_date, end_date, filters).filter(
            event_name__in=event_names,
        )
        for event_name, created_at in qs.values_list("event_name", "created_at"):
            if not event_name:
                continue
            bucket = truncate_dt(created_at, gran)
            grouped.setdefault(event_name, {})
            grouped[event_name][bucket] = grouped[event_name].get(bucket, 0) + 1
        return [
            {
                "name": name,
                "data": [
                    {"time": bucket.isoformat(), "count": count}
                    for bucket, count in sorted(grouped.get(name, {}).items())
                ],
            }
            for name in event_names
        ]

    filter_where, filter_params, _ = prepare_filters(filters or [])
    rows = raw_query(
        f"""SELECT
      we.event_name,
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS count
    FROM website_event we
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name = ANY({{eventNames::text[]}})
      {filter_where}
    GROUP BY we.event_name, 2
    ORDER BY we.event_name, 2 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventNames": event_names,
            **filter_params,
        },
    )
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in event_names}
    for row in rows:
        grouped.setdefault(row["event_name"], []).append(
            {
                "time": row["time"].isoformat()
                if isinstance(row["time"], datetime)
                else str(row["time"]),
                "count": int(row["count"] or 0),
            }
        )
    return [{"name": name, "data": grouped.get(name, [])} for name in event_names]
