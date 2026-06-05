"""CLI output formatting helpers — json, table, csv renderers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from apps.api.serializers import sanitize_for_json


def format_output(data: Any, fmt: str = "table") -> str:
    """Render data in the requested format: json, table, or csv."""
    if fmt == "json":
        return json.dumps(sanitize_for_json(data), indent=2, default=str)
    if fmt == "csv":
        return _format_csv(data)
    return _format_table(data)


def _format_table(data: Any) -> str:
    """Render a list of dicts as a simple ASCII table."""
    if isinstance(data, dict):
        for _key, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                rows = [{k: _truncate(str(v)) for k, v in row.items()} for row in value]
                return _render_rows(rows)
        items = [{k: _truncate(str(v)) for k, v in data.items()}]
        return _render_rows(items)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        rows = [{k: _truncate(str(v)) for k, v in row.items()} for row in data]
        return _render_rows(rows)

    return str(data)


def _render_rows(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "(no data)"
    headers = list(rows[0].keys())
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(row.get(h, "")))
    header_line = "  ".join(h.ljust(widths[h]) for h in headers)
    sep_line = "  ".join("-" * widths[h] for h in headers)
    data_lines = [
        "  ".join(row.get(h, "").ljust(widths[h]) for h in headers) for row in rows
    ]
    return "\n".join([header_line, sep_line, *data_lines])


def _format_csv(data: Any) -> str:
    """Render a list of dicts as CSV."""
    rows = data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                rows = value
                break
        else:
            rows = [data]

    if not isinstance(rows, list) or not rows:
        return ""
    clean = sanitize_for_json(rows)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(clean[0].keys()))
    writer.writeheader()
    writer.writerows(clean)
    return buf.getvalue().rstrip()


def _truncate(value: str, max_len: int = 50) -> str:
    if len(value) > max_len:
        return value[: max_len - 1] + "…"
    return value
