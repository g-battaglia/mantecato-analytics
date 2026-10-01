"""Per-label distinct counts with bounded Python memory."""

from __future__ import annotations

from django.core.exceptions import EmptyResultSet
from django.db import connection


def group_uniques(qs, wanted: list[str]) -> dict[str, int]:
    if not wanted:
        return {}
    try:
        sql, params = qs.order_by().values("content_groups", "visitor_key").query.sql_with_params()
    except EmptyResultSet:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"""WITH source AS ({sql})
          SELECT elem #>> '{{}}' AS label, COUNT(DISTINCT visitor_key)
          FROM source CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(content_groups) = 'array'
              THEN content_groups ELSE '[]'::jsonb END
          ) elem
          WHERE jsonb_typeof(elem) = 'string' AND elem #>> '{{}}' = ANY(%s::text[])
          GROUP BY 1""",
            [*params, wanted],
        )
        return {label: int(n) for label, n in cursor.fetchall()}
