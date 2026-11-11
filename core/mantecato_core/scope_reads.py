"""Per-label distinct counts with bounded Python memory."""

from __future__ import annotations

import re
import sys
from functools import cache

from django.core.exceptions import EmptyResultSet
from django.db import connection


@cache
def _decimal_digit_pattern() -> str:
    """Match Python's Unicode \\d even on PostgreSQL databases with C locale.

    A one-time CPU scan avoids a locale-dependent count or an unbounded Python
    visitor set. Only the small character class is retained between queries.
    """
    return "[" + "".join(chr(n) for n in range(sys.maxunicode + 1) if chr(n).isdecimal()) + "]"


def section_uniques(qs, wanted: list[str], depth: int = 2) -> dict[str, int]:
    """Return only section/count rows, never paths or visitor digests to Python.

    Mirrors section_for_path followed by _normalize_url, including repeated
    slashes, Python slicing at zero/negative depth, and Unicode decimal digits.
    DISTINCT happens after normalization: a visitor on several dynamic URLs is
    counted once, not once per pre-normalized prefix.
    """
    from core.mantecato_core.queries.stats import _PATTERNS_SMART

    if not wanted:
        return {}
    try:
        source, params = qs.order_by().values("url_path", "visitor_key").query.sql_with_params()
    except EmptyResultSet:
        return {}
    expression = "section"
    normalizer_params = []
    for pattern, replacement in _PATTERNS_SMART:
        expression = f"regexp_replace({expression}, %s, %s, %s)"
        sql_pattern = pattern.pattern.replace(r"\d", _decimal_digit_pattern())
        normalizer_params.extend([sql_pattern, replacement, "gi" if pattern.flags & re.I else "g"])
    # A streaming subquery barrier stops PostgreSQL from inlining the expensive
    # normalizer into both the filter and aggregate. Unlike MATERIALIZED, this
    # does not require retaining/spooling the entire normalized event relation.
    with connection.cursor() as cursor:
        cursor.execute(
            f"""WITH source AS ({source}), paths AS (
              SELECT visitor_key, string_to_array(btrim(split_part(split_part(
                COALESCE(NULLIF(url_path, ''), '/'), '?', 1), '#', 1), '/'), '/') AS parts
              FROM source
            ), sections AS (
              SELECT visitor_key, '/' || COALESCE(array_to_string(parts[1:
                CASE WHEN %s >= 0 THEN %s ELSE greatest(cardinality(parts) + %s, 0) END
              ], '/'), '') AS section FROM paths
            ), normalized AS (
              SELECT visitor_key, {expression} AS section FROM sections OFFSET 0
            ) SELECT section, COUNT(DISTINCT visitor_key) FROM normalized
              WHERE section = ANY(%s::text[]) GROUP BY section""",
            [*params, depth, depth, depth, *normalizer_params, wanted],
        )
        return {section: int(n) for section, n in cursor.fetchall()}


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
