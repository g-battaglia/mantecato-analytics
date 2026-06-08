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
from typing import Any

from django.db import connection
from django.db.models import Count, Max, QuerySet
from django.utils import timezone

from apps.core.models import WebsiteEvent
from core.mantecato_core.filters import Filter
from core.mantecato_core.visitor_counting import section_for_path


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


def apply_filters_to_qs(qs: QuerySet, filters: list[Filter] | None) -> QuerySet:
    """Apply privacy-first filters to a WebsiteEvent queryset."""
    for item in filters or []:
        column = item.column
        if column == "__bot_filter__":
            cfg = _parse_bot_config(item.value)
            reasons: list[str] = []
            if cfg.get("knownBots", True):
                reasons.append("known_bot_user_agent")
            if cfg.get("emptyUa", True):
                reasons.append("empty_user_agent")
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

        if column not in {
            "url_path",
            "page_title",
            "hostname",
            "browser",
            "os",
            "device",
            "country",
            "event_name",
        }:
            continue

        value = item.value
        if item.operator == "eq":
            qs = qs.filter(**{column: value})
        elif item.operator == "neq":
            qs = qs.exclude(**{column: value})
        elif item.operator == "contains":
            qs = qs.filter(**{f"{column}__icontains": value})
        elif item.operator == "not_contains":
            qs = qs.exclude(**{f"{column}__icontains": value})
        elif item.operator == "starts_with":
            qs = qs.filter(**{f"{column}__istartswith": value})
        elif item.operator == "not_starts_with":
            qs = qs.exclude(**{f"{column}__istartswith": value})
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


def empty_time_series(start_date: datetime, end_date: datetime, granularity: str) -> list[dict[str, Any]]:
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


def top_sections_from_qs(qs: QuerySet, depth: int, limit: int, normalizer: Any | None = None) -> list[dict[str, Any]]:
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
