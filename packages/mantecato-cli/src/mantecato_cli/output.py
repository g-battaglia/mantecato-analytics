"""Stable JSON/CSV output and human-readable tables."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from rich.console import Console
from rich.table import Table

from mantecato_cli.errors import UsageError


def render(data: Any, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    rows = _rows(data)
    if fmt == "csv":
        return _csv(rows, data)
    if fmt != "table":
        raise UsageError("format must be table, json, or csv")
    return _table(rows, data)


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return value
        return [data]
    if isinstance(data, list):
        return [row if isinstance(row, dict) else {"value": row} for row in data]
    return [{"value": data}]


def _csv(rows: list[dict[str, Any]], data: Any) -> str:
    headers: list[str] = []
    if not rows and isinstance(data, dict):
        query = data.get("query") or {}
        headers.extend(query.get("dimensions") or [])
        headers.extend(query.get("metrics") or [])
        if data.get("comparison") is not None:
            headers.extend(
                [
                    "current",
                    "previous",
                    "absolute_change",
                    "percentage_change",
                    "share_of_current",
                    "contribution_to_total_change",
                ]
            )
    if not rows and not headers:
        headers.append("value")
    for row in rows:
        for key in row:
            if key not in headers and not isinstance(row[key], (dict, list)):
                headers.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in headers})
    return buffer.getvalue().rstrip("\r\n")


def _table(rows: list[dict[str, Any]], data: Any) -> str:
    if not rows:
        return "(no data)"
    headers = [
        key
        for key, value in rows[0].items()
        if not isinstance(value, (dict, list)) and not key.endswith("_label")
    ]
    table = Table(show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*[_display(row.get(header)) for header in headers])
    console = Console(record=True, force_terminal=False, color_system=None, width=160)
    console.print(table)
    if isinstance(data, dict):
        query = data.get("query") or {}
        if query.get("partial"):
            console.print("Warning: the selected period contains an incomplete bucket.")
        if query.get("rows_are_overlapping"):
            console.print("Warning: content-group rows overlap and must not be summed.")
    return console.export_text().rstrip()


def _display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
