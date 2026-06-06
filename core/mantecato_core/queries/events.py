"""Custom event queries — metrics, time series, and property breakdowns.

Converted from legacy asyncpg to sync Django/psycopg3. SQL strings are unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.mantecato_core.database import raw_query
from core.mantecato_core.filters import (
    GRANULARITIES,
    Filter,
    prepare_filters,
    safe_identifier,
)


def get_event_metrics(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate custom event counts, unique visitors, and last-triggered timestamps.

    Queries the ``website_event`` table for rows with ``event_type = 2``
    (custom events, as opposed to ``event_type = 1`` for pageviews).
    Groups by ``event_name`` to produce a ranked list of the most
    frequently triggered events.

    Only events with a non-NULL ``event_name`` are included (NULL names
    indicate malformed tracker payloads).

    Args:
        website_id: UUID of the tracked website.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of event rows to return (default 50).
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts, each containing:
        - ``eventName`` (str): The custom event name.
        - ``count`` (int): Total number of times this event fired.
        - ``visitors`` (int): Unique session count.
        - ``lastTriggered`` (str | None): ISO 8601 timestamp of the
          most recent occurrence, or None if not available.
        Sorted by count descending.
    """
    filters = filters or []
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      we.event_name,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors,
      MAX(we.created_at) AS last_triggered
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name IS NOT NULL
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
            "visitors": int(row["visitors"] or 0),
            "lastTriggered": row["last_triggered"].isoformat()
            if isinstance(row["last_triggered"], datetime)
            else (str(row["last_triggered"]) if row["last_triggered"] else None),
        }
        for row in rows
    ]


def get_event_time_series(
    website_id: str,
    event_name: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    """Generate a time series of trigger counts for a specific custom event.

    Uses ``date_trunc()`` to bucket events into time intervals at the
    requested granularity.  Only intervals with at least one occurrence
    are returned; the frontend fills gaps when rendering the chart.

    The ``granularity`` parameter is validated against a whitelist and
    defaults to ``"day"`` if invalid, since it is interpolated directly
    into the SQL string.

    Args:
        website_id: UUID of the tracked website.
        event_name: Exact name of the custom event to chart.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        granularity: Time bucket size -- one of ``"minute"``,
            ``"hour"``, ``"day"``, ``"week"``, or ``"month"``.
            Defaults to ``"day"`` if invalid.
        filters: Optional list of column filters to narrow the dataset.

    Returns:
        List of dicts ordered chronologically, each containing:
        - ``time`` (str): ISO 8601 timestamp of the bucket start.
        - ``count`` (int): Number of event occurrences in this bucket.
    """
    filters = filters or []
    # granularity is interpolated into date_trunc() via f-string, so it must
    # be whitelisted (bound params can't carry an identifier).
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS count
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name = {{eventName}}
      {filter_where}
    GROUP BY 1
    ORDER BY 1 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventName": event_name,
            **filter_params,
        },
    )

    return [
        {
            "time": row["time"].isoformat()
            if isinstance(row["time"], datetime)
            else str(row["time"]),
            "count": int(row["count"] or 0),
        }
        for row in rows
    ]


def get_event_time_series_multi(
    website_id: str,
    event_names: list[str],
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Time series of trigger counts for several events in one round trip.

    Behaves exactly like calling :func:`get_event_time_series` once per
    name in *event_names* (same WHERE, same ``GROUP BY`` bucket, same
    sparse output where empty buckets are omitted), but issues a single
    query with ``event_name = ANY(...)`` instead of N sequential queries.

    Args:
        website_id: UUID of the tracked website.
        event_names: Event names to chart.  An empty list short-circuits
            to an empty result without touching the database.
        start_date: Inclusive start of the analysis window.
        end_date: Inclusive end of the analysis window.
        granularity: Bucket size; same whitelist as
            :func:`get_event_time_series` (invalid -> ``"day"``).
        filters: Optional column filters.

    Returns:
        A dict mapping each requested event name to its chronologically
        ordered ``[{"time", "count"}, ...]`` series.  Names with no
        occurrences map to an empty list.
    """
    if not event_names:
        return {}
    filters = filters or []
    gran = safe_identifier(granularity, GRANULARITIES, "day")
    filter_where, filter_params, session_join = prepare_filters(filters)

    rows = raw_query(
        f"""SELECT
      we.event_name,
      date_trunc('{gran}', we.created_at) AS time,
      COUNT(*)::bigint AS count
    FROM website_event we
    {session_join}
    WHERE we.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_type = 2
      AND we.event_name = ANY({{eventNames::text[]}})
      {filter_where}
    GROUP BY 1, 2
    ORDER BY 2 ASC""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventNames": event_names,
            **filter_params,
        },
    )

    # Pre-seed every requested name so callers always get a key back,
    # and preserve the chronological order produced by ORDER BY time.
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in event_names}
    for row in rows:
        out.setdefault(row["event_name"], []).append(
            {
                "time": row["time"].isoformat()
                if isinstance(row["time"], datetime)
                else str(row["time"]),
                "count": int(row["count"] or 0),
            }
        )
    return out


def get_event_properties(
    website_id: str,
    event_name: str,
    start_date: datetime,
    end_date: datetime,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve key-value property breakdowns for a specific custom event.

    Joins the ``event_data`` table (which stores structured properties
    sent with custom events) to ``website_event`` to produce a flat
    list of (key, value, count, visitors) tuples.  Properties can be
    either string or numeric; numeric values are cast to text for
    uniform display.

    The ``COALESCE(ed.string_value, ed.number_value::text)`` expression
    prefers the string representation when both are present (the
    tracker stores each property in the appropriate typed column).

    Args:
        website_id: UUID of the tracked website.
        event_name: Exact name of the custom event to inspect.
        start_date: Inclusive start of the analysis window.
        end_date: Exclusive end of the analysis window.
        limit: Maximum number of property rows to return (default 50).

    Returns:
        List of dicts, each containing:
        - ``dataKey`` (str): The property key name.
        - ``value`` (str | None): The property value (stringified).
        - ``count`` (int): Total occurrences of this key-value pair.
        - ``visitors`` (int): Unique session count.
        Sorted by count descending.
    """
    rows = raw_query(
        f"""SELECT
      ed.data_key,
      COALESCE(ed.string_value, ed.number_value::text) AS value,
      COUNT(*)::bigint AS count,
      COUNT(DISTINCT we.session_id)::bigint AS visitors
    FROM event_data ed
    JOIN website_event we ON ed.website_event_id = we.event_id
    WHERE ed.website_id = {{websiteId::uuid}}
      AND we.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}
      AND we.event_name = {{eventName}}
    GROUP BY 1, 2
    ORDER BY count DESC
    LIMIT {limit}""",
        {
            "websiteId": website_id,
            "startDate": start_date,
            "endDate": end_date,
            "eventName": event_name,
        },
    )

    return [
        {
            "dataKey": row["data_key"],
            "value": row["value"],
            "count": int(row["count"] or 0),
            "visitors": int(row["visitors"] or 0),
        }
        for row in rows
    ]
