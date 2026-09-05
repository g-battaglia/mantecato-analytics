"""Portable ORM fallbacks for local/dev databases.

The production query layer uses PostgreSQL-specific SQL for speed. Local
development and tests often run on SQLite, where those expressions would make
analytics pages fail before rendering. These helpers keep the same aggregate
contracts using Django ORM primitives and intentionally collect no additional
identity data.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.db import connection
from django.db.models import Count, Max, Q, QuerySet, TextField
from django.db.models.functions import Cast
from django.utils import timezone

from apps.core.models import WebsiteEvent
from core.mantecato_core.filters import (
    CONTAINMENT_COLUMNS,
    CONTAINMENT_OPERATORS,
    POSITIVE_OPERATORS,
    VALID_FILTER_COLUMNS,
)
from core.mantecato_core.visitor_counting import section_for_path

if TYPE_CHECKING:
    from core.mantecato_core.filters import Filter


def should_use_orm_fallback() -> bool:
    """Return true when raw PostgreSQL analytics SQL cannot run."""
    return connection.vendor == "sqlite"


def _parse_bot_config(value: str) -> dict[str, Any]:
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
    """Mirror build_filter_sql's ``?|`` containment for a JSON-list column.

    SQLite has neither jsonb operators nor a JSON ``contains`` lookup, so
    membership is tested against the serialised document: a label is matched as
    its own quoted JSON token (``"guides"``), which cannot collide with a longer
    label that merely starts the same way (``"guides-advanced"``). Labels are
    serialised with :func:`json.dumps` so any quoting inside them lines up with
    how the value was stored.
    """
    if operator not in CONTAINMENT_OPERATORS:
        return None
    text_column = f"{json_column}_text"
    if operator in ("starts_with", "not_starts_with"):
        # A member always starts right after its opening quote, so searching for
        # '"cat:' anchors the prefix to the start of a label — it cannot match
        # mid-label the way a bare substring would.
        match = Q(**{f"{text_column}__contains": f'"{value}'})
        return match if operator == "starts_with" else ~match
    values = (
        [v.strip() for v in (value.split(",") if value else []) if v.strip()]
        if operator in ("in", "not_in")
        else [value]
    )
    if not values:
        return Q(pk__in=[]) if operator == "in" else None
    match = Q()
    for label in values:
        match |= Q(**{f"{text_column}__contains": json.dumps(label)})
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
        if item.column in CONTAINMENT_COLUMNS:
            # The JSON document is matched as text (see _containment_q), which
            # needs the column cast once per query.
            json_column = CONTAINMENT_COLUMNS[item.column]
            qs = qs.annotate(**{f"{json_column}_text": Cast(json_column, output_field=TextField())})
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


def coerce_dt(value: datetime) -> datetime:
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def truncate_dt(value: datetime, granularity: str) -> datetime:
    """Truncate a datetime to a supported analytics bucket."""
    value = coerce_dt(value)
    if granularity == "minute":
        return value.replace(second=0, microsecond=0)
    if granularity == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if granularity == "week":
        start = value - timedelta(days=value.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def next_bucket(value: datetime, granularity: str) -> datetime:
    if granularity == "minute":
        return value + timedelta(minutes=1)
    if granularity == "hour":
        return value + timedelta(hours=1)
    if granularity == "week":
        return value + timedelta(weeks=1)
    if granularity == "month":
        year = value.year + (1 if value.month == 12 else 0)
        month = 1 if value.month == 12 else value.month + 1
        return value.replace(year=year, month=month, day=1)
    return value + timedelta(days=1)


def empty_time_series(
    start_date: datetime, end_date: datetime, granularity: str
) -> list[dict[str, Any]]:
    """Build gapless time buckets with zero pageviews."""
    rows: list[dict[str, Any]] = []
    current = truncate_dt(start_date, granularity)
    end_bucket = truncate_dt(end_date, granularity)
    while current <= end_bucket:
        rows.append({"time": current.isoformat(), "pageviews": 0})
        current = next_bucket(current, granularity)
    return rows


def pageview_time_series_rows(
    website_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str,
    filters: list[Filter] | None = None,
) -> list[dict[str, Any]]:
    buckets = {
        datetime.fromisoformat(row["time"]): row
        for row in empty_time_series(start_date, end_date, granularity)
    }
    for created_at in pageview_queryset(website_id, start_date, end_date, filters).values_list(
        "created_at",
        flat=True,
    ):
        bucket = truncate_dt(created_at, granularity)
        if bucket not in buckets:
            buckets[bucket] = {"time": bucket.isoformat(), "pageviews": 0}
        buckets[bucket]["pageviews"] += 1
    return [buckets[key] for key in sorted(buckets)]


def stats_dict(qs: QuerySet) -> dict[str, int]:
    pageviews = qs.count()
    bot_pageviews = qs.filter(is_bot=True).count()
    return {
        "pageviews": pageviews,
        "human_pageviews": pageviews - bot_pageviews,
        "bot_pageviews": bot_pageviews,
    }


def count_by_field(qs: QuerySet, field: str, count_key: str, limit: int) -> list[dict[str, Any]]:
    rows = (
        qs.exclude(**{f"{field}__isnull": True})
        .exclude(**{field: ""})
        .values(field)
        .annotate(total=Count("event_id"))
        .order_by("-total", field)[:limit]
    )
    return [
        {
            "value": row[field],
            count_key: int(row["total"] or 0),
        }
        for row in rows
    ]


def top_sections_from_qs(
    qs: QuerySet, depth: int, limit: int, normalizer: Any | None = None
) -> list[dict[str, Any]]:
    counter: dict[str, int] = defaultdict(int)
    pages: dict[str, set[str]] = defaultdict(set)
    for path in qs.values_list("url_path", flat=True):
        section = section_for_path(path or "/", depth=depth)
        if normalizer is not None:
            section = normalizer(section)
        counter[section] += 1
        pages[section].add(path or "/")
    rows = [
        {"section": section, "views": views, "pages": len(pages[section])}
        for section, views in counter.items()
    ]
    rows.sort(key=lambda row: (-row["views"], row["section"]))
    return rows[:limit]


def top_groups_from_qs(qs: QuerySet, limit: int) -> list[dict[str, Any]]:
    """SQLite mirror of the ``jsonb_array_elements_text`` group aggregation.

    One row per label; a pageview declaring several labels counts once in each,
    so the totals overlap by design. Rows with no (or a malformed) group list
    are skipped rather than bucketed together.
    """
    counter: dict[str, int] = defaultdict(int)
    pages: dict[str, set[str]] = defaultdict(set)
    for groups, path in qs.values_list("content_groups", "url_path"):
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, str) or not group:
                continue
            counter[group] += 1
            pages[group].add(path or "/")
    rows = [
        {"group": group, "views": views, "pages": len(pages[group])}
        for group, views in counter.items()
    ]
    rows.sort(key=lambda row: (-row["views"], row["group"]))
    return rows[:limit]


def heatmap_rows(qs: QuerySet) -> list[dict[str, Any]]:
    counter: Counter[tuple[int, int]] = Counter()
    for created_at in qs.values_list("created_at", flat=True):
        value = coerce_dt(created_at)
        day_of_week = (value.weekday() + 1) % 7
        counter[(day_of_week, value.hour)] += 1
    return [
        {"dayOfWeek": day, "hour": hour, "pageviews": count}
        for (day, hour), count in sorted(counter.items())
    ]


def event_metric_rows(qs: QuerySet, limit: int) -> list[dict[str, Any]]:
    rows = (
        qs.exclude(event_name__isnull=True)
        .exclude(event_name="")
        .values("event_name")
        .annotate(total=Count("event_id"), last_triggered=Max("created_at"))
        .order_by("-total", "event_name")[:limit]
    )
    return [
        {
            "eventName": row["event_name"],
            "count": int(row["total"] or 0),
            "lastTriggered": row["last_triggered"].isoformat() if row["last_triggered"] else "",
        }
        for row in rows
    ]
