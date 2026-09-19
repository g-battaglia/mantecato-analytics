"""Bounded SQL for API v1 analytics without changing the legacy query engine."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from apps.api.v1.catalog import MAX_CARDINALITY
from apps.api.v1.execution import fetch_all

if TYPE_CHECKING:
    from apps.api.v1.contracts import FilterSpec, QuerySpec, ResolvedRange

_SIMPLE_DIMENSIONS = {
    "country": "we.country",
    "referrer_domain": "we.referrer_domain",
    "browser": "we.browser",
    "os": "we.os",
    "device": "we.device",
    "hostname": "we.hostname",
    "url_path": "we.url_path",
    "page_title": "we.page_title",
    "event_name": "we.event_name",
}


def aggregate(
    spec: QuerySpec,
    *,
    date_range: ResolvedRange | None = None,
    hard_limit: int = MAX_CARDINALITY,
) -> tuple[list[dict[str, Any]], bool]:
    """Return aggregate rows and whether the bounded candidate set overflowed."""
    active = replace(spec, date_range=date_range or spec.date_range)
    sql, params = _aggregate_sql(active, hard_limit=hard_limit)
    rows = fetch_all(sql, params)
    truncated = len(rows) > hard_limit
    rows = rows[:hard_limit]
    return [_shape_row(row, active) for row in rows], truncated


def dimension_values(spec: QuerySpec, dimension: str, search: str | None = None) -> list[dict]:
    """Return bounded distinct values for one dimension."""
    value_spec = replace(
        spec,
        operation="breakdown",
        dimensions=(dimension,),
        metrics=("events",) if dimension == "event_name" else ("pageviews",),
    )
    rows, truncated = aggregate(value_spec, hard_limit=min(spec.limit, 500))
    result = [
        {
            "value": row.get(dimension),
            "label": _dimension_label(dimension, row.get(dimension)),
        }
        for row in rows
        if search is None or search.lower() in str(row.get(dimension) or "").lower()
    ]
    return [{**row, "truncated": truncated} for row in result[: spec.limit]]


def _aggregate_sql(spec: QuerySpec, *, hard_limit: int) -> tuple[str, list[object]]:
    dims = list(spec.dimensions)
    dimension_selects, joins, dimension_params = _dimension_sources(spec)
    filters_sql, filter_params = _filter_groups_sql(spec.filter_groups)
    event_type = 2 if spec.dataset == "events" else 1
    base_params: list[object] = [
        *dimension_params,
        spec.website_id,
        spec.date_range.start,
        spec.date_range.end,
        event_type,
        *filter_params,
    ]

    source_dim_select = ", ".join(dimension_selects)
    if source_dim_select:
        source_dim_select = ", " + source_dim_select
    quoted_dims = [_quote(dimension) for dimension in dims]
    time_expression = _bucket_expression(spec)
    if time_expression:
        source_time = f", {time_expression} AS bucket"
        event_keys = ["bucket", *dims]
    else:
        source_time = ""
        event_keys = dims

    event_group = f"GROUP BY {', '.join(_quote(key) for key in event_keys)}" if event_keys else ""
    event_key_select = f"{', '.join(_quote(key) for key in event_keys)}, " if event_keys else ""

    partition_fields = [*quoted_dims, "visitor_key"]
    partition = ", ".join(partition_fields)
    session_dim_select = f"{', '.join(quoted_dims)}, " if quoted_dims else ""
    session_dim_group = f", {', '.join(quoted_dims)}" if quoted_dims else ""
    session_keys = [*dims]
    if time_expression:
        session_bucket = _bucket_expression(spec, column="session_start")
        session_keys = ["bucket", *session_keys]
        session_key_select = f"{session_bucket} AS bucket"
        if quoted_dims:
            session_key_select += f", {', '.join(quoted_dims)}"
    else:
        session_key_select = ", ".join(quoted_dims)
    session_group = (
        f"GROUP BY {', '.join(_quote(key) for key in session_keys)}" if session_keys else ""
    )

    join_condition = _join_condition(event_keys, left="e", right="s")
    final_keys = f"{', '.join(f'e.{_quote(key)}' for key in event_keys)}, " if event_keys else ""
    order = _order_clause(spec, event_keys)

    # Sessions apply only to pageviews. Custom-event responses keep these fields
    # null and never claim visit semantics from event names.
    session_ctes = ""
    session_join = ""
    session_columns = (
        "NULL::bigint AS visits, NULL::bigint AS bounces, NULL::double precision AS total_duration"
    )
    if spec.dataset == "pageviews":
        session_ctes = f""",
    marked AS (
      SELECT *, LAG(created_at) OVER (
        PARTITION BY {partition} ORDER BY created_at, event_id
      ) AS previous_at
      FROM source
      WHERE visitor_key IS NOT NULL
    ),
    numbered AS (
      SELECT *, SUM(
        CASE WHEN previous_at IS NULL OR created_at - previous_at > INTERVAL '30 minutes'
             THEN 1 ELSE 0 END
      ) OVER (
        PARTITION BY {partition} ORDER BY created_at, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      ) AS session_no
      FROM marked
    ),
    sessions AS (
      SELECT {session_dim_select}visitor_key, session_no,
             MIN(created_at) AS session_start,
             COUNT(*)::bigint AS session_pageviews,
             EXTRACT(EPOCH FROM MAX(created_at) - MIN(created_at))::double precision AS duration
      FROM numbered
      GROUP BY visitor_key, session_no{session_dim_group}
    ),
    session_agg AS (
      SELECT {session_key_select + "," if session_key_select else ""}
             COUNT(*)::bigint AS visits,
             COUNT(*) FILTER (WHERE session_pageviews = 1)::bigint AS bounces,
             COALESCE(SUM(duration), 0)::double precision AS total_duration
      FROM sessions
      {session_group}
    )"""
        session_join = (
            f"LEFT JOIN session_agg s ON {join_condition}"
            if event_keys
            else "CROSS JOIN session_agg s"
        )
        session_columns = (
            "COALESCE(s.visits, 0)::bigint AS visits, "
            "COALESCE(s.bounces, 0)::bigint AS bounces, "
            "COALESCE(s.total_duration, 0)::double precision AS total_duration"
        )

    sql = f"""WITH source AS (
      SELECT we.event_id, we.created_at, we.visitor_key, we.is_bot,
             we.referrer_domain AS source_referrer_domain{source_dim_select}{source_time}
      FROM website_event we
      {" ".join(joins)}
      WHERE we.website_id = %s::uuid
        AND we.created_at >= %s::timestamptz
        AND we.created_at < %s::timestamptz
        AND we.event_type = %s
        {filters_sql}
    ),
    event_agg AS (
      SELECT {event_key_select}
             COUNT(*)::bigint AS event_count,
             COUNT(*) FILTER (WHERE COALESCE(is_bot, false) = false)::bigint AS human_count,
             COUNT(*) FILTER (WHERE COALESCE(is_bot, false) = true)::bigint AS bot_count,
             COUNT(*) FILTER (
               WHERE source_referrer_domain IS NULL OR source_referrer_domain = ''
             )::bigint
               AS direct_count,
             COUNT(DISTINCT ((created_at AT TIME ZONE 'UTC')::date, visitor_key))
               FILTER (WHERE visitor_key IS NOT NULL)::bigint AS daily_unique_visitors,
             COUNT(*) FILTER (WHERE visitor_key IS NULL)::bigint AS missing_visitor_keys
      FROM source
      {event_group}
    )
    {session_ctes}
    SELECT {final_keys}e.event_count, e.human_count, e.bot_count, e.direct_count,
           e.daily_unique_visitors, e.missing_visitor_keys,
           {session_columns}
    FROM event_agg e
    {session_join}
    {order}
    LIMIT {int(hard_limit) + 1}"""
    return sql, base_params


def _dimension_sources(spec: QuerySpec) -> tuple[list[str], list[str], list[object]]:
    selects: list[str] = []
    joins: list[str] = []
    params: list[object] = []
    for dimension in spec.dimensions:
        if dimension in _SIMPLE_DIMENSIONS:
            selects.append(f'{_SIMPLE_DIMENSIONS[dimension]} AS "{dimension}"')
        elif dimension == "section":
            depth = int(spec.section_depth) + 1
            clean = "REGEXP_REPLACE(SPLIT_PART(SPLIT_PART(we.url_path, '?', 1), '#', 1), '/+$', '')"
            expression = (
                "COALESCE(NULLIF(array_to_string((string_to_array("
                f"{clean}, '/'))[1:{depth}], '/'), ''), '/')"
            )
            selects.append(f'{expression} AS "section"')
        elif dimension == "content_group":
            selector = ""
            if spec.dimension_prefix:
                selector = " AND elem #>> '{}' LIKE %s"
                params.append(f"{spec.dimension_prefix}%")
            elif spec.dimension_exact:
                selector = " AND elem #>> '{}' = %s"
                params.append(spec.dimension_exact)
            joins.append(
                """CROSS JOIN LATERAL (
                  SELECT DISTINCT elem #>> '{}' AS value
                  FROM jsonb_array_elements(
                    CASE WHEN jsonb_typeof(we.content_groups) = 'array'
                         THEN we.content_groups ELSE '[]'::jsonb END
                  ) elem
                  WHERE jsonb_typeof(elem) = 'string' AND elem #>> '{}' <> ''"""
                + selector
                + "\n                ) content_group_value"
            )
            selects.append('content_group_value.value AS "content_group"')
    return selects, joins, params


def _bucket_expression(spec: QuerySpec, *, column: str = "created_at") -> str | None:
    if not spec.granularity:
        return None
    timezone = spec.date_range.timezone.replace("'", "''")
    granularity = spec.granularity
    return (
        f"date_trunc('{granularity}', {column} AT TIME ZONE '{timezone}') AT TIME ZONE '{timezone}'"
    )


def _filter_groups_sql(
    groups: tuple[tuple[FilterSpec, ...], ...],
) -> tuple[str, list[object]]:
    params: list[object] = []
    group_clauses: list[str] = []
    for group in groups:
        by_column: dict[str, list[FilterSpec]] = {}
        for item in group:
            by_column.setdefault(item.column, []).append(item)
        column_clauses: list[str] = []
        for _column, items in by_column.items():
            positives: list[str] = []
            negatives: list[str] = []
            positive_params: list[object] = []
            negative_params: list[object] = []
            for item in items:
                clause, values, positive = _filter_clause(item)
                (positives if positive else negatives).append(clause)
                (positive_params if positive else negative_params).extend(values)
            params.extend(positive_params)
            params.extend(negative_params)
            parts: list[str] = []
            if positives:
                parts.append(f"({' OR '.join(positives)})")
            parts.extend(negatives)
            if parts:
                column_clauses.append(f"({' AND '.join(parts)})")
        if column_clauses:
            group_clauses.append(f"({' AND '.join(column_clauses)})")
    return ("AND " + " AND ".join(group_clauses), params) if group_clauses else ("", params)


def _filter_clause(item: FilterSpec) -> tuple[str, list[object], bool]:
    positive = item.operator in ("eq", "contains", "starts_with", "in")
    if item.column == "content_group":
        if item.operator in ("starts_with", "not_starts_with"):
            exists = """EXISTS (
              SELECT 1 FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(we.content_groups) = 'array'
                     THEN we.content_groups ELSE '[]'::jsonb END
              ) elem
              WHERE jsonb_typeof(elem) = 'string' AND elem #>> '{}' ILIKE %s
            )"""
            clause = exists if item.operator == "starts_with" else f"NOT ({exists})"
            return clause, [f"{item.values[0]}%"], positive
        placeholders = ", ".join(["%s"] * len(item.values))
        exists = f"""EXISTS (
          SELECT 1 FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(we.content_groups) = 'array'
                 THEN we.content_groups ELSE '[]'::jsonb END
          ) elem
          WHERE jsonb_typeof(elem) = 'string' AND elem #>> '{{}}' IN ({placeholders})
        )"""
        clause = exists if positive else f"NOT ({exists})"
        return clause, list(item.values), positive

    expression = "we.is_bot" if item.column == "is_bot" else f"we.{item.column}"
    values: list[object] = list(item.values)
    if item.column == "is_bot":
        values = [item.values[0] == "true"]
    if item.operator == "eq":
        return f"{expression} = %s", values, positive
    if item.operator == "neq":
        return f"({expression} IS NULL OR {expression} <> %s)", values, positive
    if item.operator in ("contains", "not_contains", "starts_with", "not_starts_with"):
        pattern = f"%{item.values[0]}%" if "contains" in item.operator else f"{item.values[0]}%"
        clause = f"{expression} ILIKE %s"
        if item.operator.startswith("not_"):
            clause = f"({expression} IS NULL OR {expression} NOT ILIKE %s)"
        return clause, [pattern], positive
    placeholders = ", ".join(["%s"] * len(values))
    if item.operator == "in":
        return f"{expression} IN ({placeholders})", values, positive
    return f"({expression} IS NULL OR {expression} NOT IN ({placeholders}))", values, positive


def _quote(identifier: str) -> str:
    return f'"{identifier}"'


def _join_condition(keys: list[str], *, left: str, right: str) -> str:
    if not keys:
        return "TRUE"
    return " AND ".join(
        f"{left}.{_quote(key)} IS NOT DISTINCT FROM {right}.{_quote(key)}" for key in keys
    )


def _order_clause(spec: QuerySpec, keys: list[str]) -> str:
    if spec.operation == "timeseries":
        order = [f"e.{_quote(key)} ASC NULLS FIRST" for key in keys]
        return "ORDER BY " + ", ".join(order)
    if spec.operation == "breakdown":
        return "ORDER BY e.event_count DESC, " + ", ".join(
            f"e.{_quote(key)} ASC NULLS FIRST" for key in keys
        )
    return ""


def _shape_row(row: dict[str, Any], spec: QuerySpec) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if spec.granularity:
        bucket = row.get("bucket")
        output["time"] = bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket)
    for dimension in spec.dimensions:
        value = row.get(dimension)
        output[dimension] = value
        output[f"{dimension}_label"] = _dimension_label(dimension, value)

    event_count = int(row.get("event_count") or 0)
    missing_keys = int(row.get("missing_visitor_keys") or 0)
    visits = int(row.get("visits") or 0) if spec.dataset == "pageviews" else None
    bounces = int(row.get("bounces") or 0) if spec.dataset == "pageviews" else None
    duration = float(row.get("total_duration") or 0) if spec.dataset == "pageviews" else None
    unavailable: dict[str, str] = {}

    values: dict[str, Any] = {
        "pageviews": event_count if spec.dataset == "pageviews" else None,
        "events": event_count if spec.dataset == "events" else None,
        "human_pageviews": int(row.get("human_count") or 0)
        if spec.dataset == "pageviews"
        else None,
        "bot_pageviews": int(row.get("bot_count") or 0) if spec.dataset == "pageviews" else None,
        "daily_unique_visitors": int(row.get("daily_unique_visitors") or 0),
        "visits": visits,
        "bounces": bounces,
        "bounce_rate": round(bounces / visits * 100, 6) if visits else 0.0,
        "total_duration": duration,
        "average_visit_duration": round(duration / visits, 6) if visits else 0.0,
        "pages_per_visit": round(event_count / visits, 6) if visits else 0.0,
    }
    if missing_keys:
        reason = "visitor_keys_unavailable_for_part_of_range"
        for metric in (
            "daily_unique_visitors",
            "visits",
            "bounces",
            "bounce_rate",
            "total_duration",
            "average_visit_duration",
            "pages_per_visit",
        ):
            if metric in spec.metrics:
                values[metric] = None
                unavailable[metric] = reason
    for metric in spec.metrics:
        output[metric] = values[metric]
    if unavailable:
        output["unavailable_reasons"] = unavailable
    output["_direct_count"] = int(row.get("direct_count") or 0)
    output["_missing_visitor_keys"] = missing_keys
    return output


def _dimension_label(dimension: str, value: object) -> str:
    if value is not None and str(value) != "":
        return str(value)
    if dimension == "referrer_domain":
        return "(direct)"
    return "(not set)"
