"""Event querysets with the privacy-first filter pipeline.

The visitor-counting read path filters ``website_event`` rows through Django
ORM querysets even on PostgreSQL (per-scope digests, landing metrics, hourly
buckets), so the filter translation lives here as first-class production code.
Raw-SQL analytics queries keep using :func:`build_filter_sql` directly.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet
from django.db.models.expressions import RawSQL

from apps.core.models import WebsiteEvent
from core.mantecato_core.filters import (
    CONTAINMENT_COLUMNS,
    CONTAINMENT_OPERATORS,
    POSITIVE_OPERATORS,
    VALID_FILTER_COLUMNS,
)

if TYPE_CHECKING:
    from datetime import datetime

    from core.mantecato_core.filters import Filter


def _parse_bot_config(value: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        payload = {}
    cfg = payload.get("config", payload) if isinstance(payload, dict) else {}
    return cfg if isinstance(cfg, dict) else {}


def _filter_q(column: str, operator: str, value: str) -> Q | None:
    """Translate one Filter into a Django ``Q`` (mirrors build_filter_sql)."""
    if column in CONTAINMENT_COLUMNS:
        return _containment_q(CONTAINMENT_COLUMNS[column], operator, value)
    if operator == "eq":
        return Q(**{column: value})
    if operator == "neq":
        return ~Q(**{column: value})
    if operator == "contains":
        return Q(**{f"{column}__icontains": value})
    if operator == "not_contains":
        return ~Q(**{f"{column}__icontains": value})
    if operator == "starts_with":
        return Q(**{f"{column}__istartswith": value})
    if operator == "not_starts_with":
        return ~Q(**{f"{column}__istartswith": value})
    if operator in ("in", "not_in"):
        values = [v.strip() for v in (value.split(",") if value else []) if v.strip()]
        if not values:
            # Mirror build_filter_sql: empty `in` matches nothing (never drop →
            # match-all); empty `not_in` excludes nothing (no-op).
            return Q(pk__in=[]) if operator == "in" else None
        q = Q(**{f"{column}__in": values})
        # Mirror build_filter_sql's not_in (``col IS NULL OR col <> ALL(...)``),
        # which keeps NULL rows — ``~Q(col__in=...)`` alone would drop them.
        return q if operator == "in" else (Q(**{f"{column}__isnull": True}) | ~q)
    return None


def _containment_q(json_column: str, operator: str, value: str) -> Q | None:
    """Mirror build_filter_sql's containment for a JSON-list column.

    The members are expanded and matched one at a time. Substring-matching the
    serialised document would be simpler but wrong: it cannot tell a top-level
    label from a string buried in a nested object, so ``[{"nested": "guides"}]``
    would answer to ``content_group=guides`` while the aggregation — which
    counts only top-level string members — never reports that label at all.

    The array guard and the string-type test mirror the aggregation query's, so
    this path and the raw-SQL one answer with the same rows.
    """
    if operator not in CONTAINMENT_OPERATORS:
        return None

    prefix_match = operator in ("starts_with", "not_starts_with")
    if prefix_match:
        params: list[str] = [f"{value}%"]
    else:
        params = (
            [v.strip() for v in (value.split(",") if value else []) if v.strip()]
            if operator in ("in", "not_in")
            else [value]
        )
        if not params:
            return Q(pk__in=[]) if operator == "in" else None

    member = "je.v #>> '{}'"
    source = (
        f"LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(we.{json_column}) = 'array' "
        f"THEN we.{json_column} ELSE '[]'::jsonb END) AS je(v)"
    )
    type_guard = "jsonb_typeof(je.v) = 'string'"

    predicate = (
        f"{member} ILIKE %s" if prefix_match else f"{member} IN ({', '.join(['%s'] * len(params))})"
    )
    match = Q(
        pk__in=RawSQL(  # noqa: S611 — no interpolation of user input: values are bound params
            f"""SELECT we.event_id FROM website_event we, {source}
                WHERE {type_guard} AND {predicate}""",
            params,
        )
    )
    if operator in POSITIVE_OPERATORS:
        return match
    # Negated: keep rows with no labels at all, like the SQL branch does.
    return Q(**{f"{json_column}__isnull": True}) | ~match


def apply_filters_to_qs(qs: QuerySet, filters: list[Filter] | None) -> QuerySet:
    """Apply privacy-first filters to a WebsiteEvent queryset.

    Mirrors ``build_filter_sql``: within a column, **positive** filters OR
    together ("/trial/ OR /pro/") while **negated** filters AND together
    (exclude BOTH /admin/ AND /login/ — OR-ing negations would match every row).
    Different columns are AND-ed.
    """
    grouped: dict[str, list[tuple[str, Q]]] = defaultdict(list)
    for item in filters or []:
        if item.column == "__bot_filter__":
            cfg = _parse_bot_config(item.value)
            reasons: list[str] = []
            if cfg.get("knownBots", True):
                reasons.append("known_bot_user_agent")
            if cfg.get("emptyUa", True):
                reasons.append("empty_user_agent")
            if cfg.get("datacenterIps", True):
                reasons.append("datacenter_ip")
            if reasons:
                qs = qs.exclude(bot_reason__in=reasons)
            countries = [
                str(code).upper()
                for code in cfg.get("excludedCountries", [])
                if isinstance(code, str) and len(code) == 2
            ]
            if countries:
                qs = qs.exclude(country__in=countries)
            continue

        if item.column not in VALID_FILTER_COLUMNS:
            continue
        q = _filter_q(item.column, item.operator, item.value)
        if q is not None:
            grouped[item.column].append((item.operator, q))

    for column_qs in grouped.values():
        positives = [q for op, q in column_qs if op in POSITIVE_OPERATORS]
        negatives = [q for op, q in column_qs if op not in POSITIVE_OPERATORS]
        combined: Q | None = None
        if positives:
            combined = positives[0]
            for extra in positives[1:]:
                combined |= extra  # inclusive: /trial/ OR /pro/
        for nq in negatives:
            combined = nq if combined is None else (combined & nq)  # exclusions AND
        if combined is not None:
            qs = qs.filter(combined)
    return qs


def event_queryset(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    *,
    event_type: int,
    filters: list[Filter] | None = None,
) -> QuerySet:
    """Return a filtered WebsiteEvent queryset for aggregate reads."""
    qs = WebsiteEvent.objects.filter(
        website_id=website_id,
        created_at__gte=start_date,
        created_at__lte=end_date,
        event_type=event_type,
    )
    return apply_filters_to_qs(qs, filters)


def pageview_queryset(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> QuerySet:
    return event_queryset(website_id, start_date, end_date, event_type=1, filters=filters)


def custom_event_queryset(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    filters: list[Filter] | None = None,
) -> QuerySet:
    return event_queryset(website_id, start_date, end_date, event_type=2, filters=filters)
