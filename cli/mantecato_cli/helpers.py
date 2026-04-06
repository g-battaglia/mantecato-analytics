from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from mantecato_core.database import get_pool
from mantecato_core.helpers import (  # noqa: F401
    compute_derived_stats,
    format_duration,
    format_percent,
    list_sites,
    num,
    parse_date_args,
    parse_filter_args,
    pct_change,
    resolve_granularity_arg,
    resolve_site_id,
    resolve_user_id,
)


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


def format_output(data: Any, fmt: str = "table", title: str | None = None) -> str:
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


async def run_with_db(coro):
    from mantecato_core.database import close_pool, create_pool
    from mantecato_cli.config import get_database_url

    try:
        db_url = get_database_url()
        if db_url:
            await create_pool(dsn=db_url)
        else:
            await get_pool()
        return await coro
    finally:
        await close_pool()
