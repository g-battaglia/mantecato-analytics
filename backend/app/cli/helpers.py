from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from ..database import get_pool, raw_query
from ..date_utils import DateRange, resolve_date_range, resolve_granularity
from ..filters import Filter, parse_filters_from_params


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
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=365),
            datetime.now(timezone.utc),
        )
    return range_


def parse_filter_args(filter_strs: list[str]) -> list[Filter]:
    if not filter_strs:
        return []
    return parse_filters_from_params(filter_strs)


def resolve_granularity_arg(granularity: str, range_: DateRange) -> str:
    return resolve_granularity(granularity, range_)


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


def compute_derived_stats(raw: dict[str, Any]) -> dict[str, Any]:
    pageviews = raw.get("pageviews", 0) or 0
    visitors = raw.get("visitors", 0) or 0
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


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return " -> ".join(str(v) for v in value)
    return str(value)


def format_output(
    data: Any, fmt: str = "table", title: str | None = None
) -> str:
    if data is None:
        return ""

    if fmt == "json":
        return json.dumps(data, indent=2, default=str)

    if fmt == "csv":
        return _format_csv(data)

    return _format_table(data, title)


def _format_csv(data: Any) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    if isinstance(data, dict):
        writer.writerow(["key", "value"])
        for k, v in data.items():
            writer.writerow([k, format_value(v)])
    elif isinstance(data, list) and data:
        keys = list(data[0].keys())
        writer.writerow(keys)
        for row in data:
            writer.writerow([format_value(row.get(k)) for k in keys])

    return buf.getvalue().rstrip("\n")


def _format_table(data: Any, title: str | None = None) -> str:
    lines: list[str] = []

    if title:
        lines.append(title)
        lines.append("=" * len(title))

    if isinstance(data, dict):
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        for k, v in data.items():
            lines.append(f"{str(k):<{max_key_len}}  {format_value(v)}")

    elif isinstance(data, list) and data:
        keys = list(data[0].keys())
        col_widths = {}
        for k in keys:
            max_val = max(len(format_value(row.get(k))) for row in data) if data else 0
            col_widths[k] = min(max(len(k), max_val), 60)

        header = "  ".join(f"{k:<{col_widths[k]}}" for k in keys)
        lines.append(header)
        lines.append("-" * len(header))

        for row in data:
            vals = []
            for k in keys:
                v = format_value(row.get(k))
                if len(v) > 60:
                    v = v[:57] + "..."
                vals.append(f"{v:<{col_widths[k]}}")
            lines.append("  ".join(vals))

        lines.append(f"({len(data)} rows)")

    return "\n".join(lines)


async def resolve_user_id(api_key_override: str | None = None) -> str:
    from ..queries.api_keys import validate_api_key

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


async def run_with_db(coro):
    from ..database import close_pool

    try:
        await get_pool()
        return await coro
    finally:
        await close_pool()
