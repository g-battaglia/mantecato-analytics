"""Shared helper functions for CLI, MCP, and other consumers of mantecato-core."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import get_pool
from .date_utils import DateRange, resolve_date_range, resolve_granularity
from .filters import Filter, parse_filters_from_params


async def list_sites() -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT website_id, name, domain FROM website WHERE deleted_at IS NULL ORDER BY name"
    )
    return [
        {"website_id": str(r["website_id"]), "name": r["name"], "domain": r["domain"]}
        for r in rows
    ]


async def resolve_site_id(site: str) -> str:
    sites = await list_sites()

    # Exact match (case-insensitive)
    for s in sites:
        if site.lower() in (
            s["website_id"].lower(),
            s["name"].lower(),
            s["domain"].lower(),
        ):
            return s["website_id"]

    # Partial/substring match
    for s in sites:
        if site.lower() in s["name"].lower() or site.lower() in s["domain"].lower():
            return s["website_id"]

    available = ", ".join(f"{s['name']} ({s['domain']})" for s in sites)
    raise SystemExit(f"Site not found: {site}\nAvailable sites: {available}")


def parse_date_args(
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> DateRange:
    if start and end:
        return DateRange(
            datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
            datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
        )
    if start:
        return DateRange(
            datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
            datetime.now(timezone.utc),
        )

    preset = period or "30d"
    range_ = resolve_date_range(preset)
    if range_ is None:
        # Fallback for unknown presets
        range_ = DateRange(
            datetime.now(timezone.utc) - timedelta(days=365),
            datetime.now(timezone.utc),
        )
    return range_


def parse_filter_args(filter_strs: list[str]) -> list[Filter]:
    if not filter_strs:
        return []
    return parse_filters_from_params(filter_strs)


def resolve_granularity_arg(granularity: str, range_: DateRange) -> str:
    return resolve_granularity(granularity, range_)


def compute_derived_stats(raw: dict[str, Any]) -> dict[str, Any]:
    pageviews = raw.get("pageviews", 0) or 0
    _visitors = raw.get("visitors", 0) or 0
    visits = raw.get("visits", 0) or 0
    bounces = raw.get("bounces", 0) or 0
    total_duration = raw.get("total_duration", 0) or 0

    bounce_rate = (bounces / visits * 100) if visits > 0 else 0
    avg_duration = total_duration / visits if visits > 0 else 0
    pages_per_visit = pageviews / visits if visits > 0 else 0

    return {
        **raw,
        "bounce_rate": round(bounce_rate, 1),
        "avg_duration": round(avg_duration, 1),
        "pages_per_visit": round(pages_per_visit, 2),
    }


async def resolve_user_id(api_key_override: str | None = None) -> str:
    from .queries.api_keys import validate_api_key

    key = api_key_override or os.environ.get("MANTECATO_API_KEY")
    if not key:
        raise SystemExit(
            "Error: API key required. Set MANTECATO_API_KEY or use --api-key.\n"
            "Generate one in Settings > API Keys > New Key."
        )

    result = await validate_api_key(key)
    if not result:
        raise SystemExit("Error: Invalid API key.")
    return result["userId"]


def num(n: int | float | None) -> str:
    if n is None:
        return "-"
    return f"{int(n):,}"


def pct_change(current: float | int | None, previous: float | int | None) -> str:
    if current is None or previous is None or previous == 0:
        if current is not None and previous == 0 and current > 0:
            return "+New"
        return "-"
    change = ((current - previous) / previous) * 100
    if change >= 0:
        return f"+{change:.1f}%"
    return f"{change:.1f}%"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"
