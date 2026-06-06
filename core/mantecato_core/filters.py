"""SQL filter builder — privacy-first aggregate mode.

Simplified from the original: no session joins, no bot session detection,
no referrer/UTM columns. Filters operate directly on website_event columns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SESSION_COLUMNS: list[str] = []

VALID_FILTER_COLUMNS: set[str] = {
    "url_path",
    "page_title",
    "hostname",
    "browser",
    "os",
    "device",
    "country",
}

VALID_OPERATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "not_starts_with",
}

GRANULARITIES = ("minute", "hour", "day", "week", "month")

# Bot detection config is retained for future use but in privacy-first
# mode there are no sessions to filter. The functions below return no-ops.
BOT_BROWSER_PATTERN = (
    "%(bot|crawler|spider|scraper|headless|phantom|selenium|puppeteer"
    "|wget|curl|python|go-http|java|libwww|fetcher|slurp"
    "|googlebot|bingbot|yandex|baidu|facebookexternalhit"
    "|twitterbot|linkedinbot|whatsapp|telegrambot|discordbot"
    "|applebot|semrush|ahrefs|mj12bot|dotbot|petalbot"
    "|bytespider|gptbot|claudebot|chatgpt|searchbot)%"
)


def safe_identifier(value: str, allowed: tuple[str, ...], default: str) -> str:
    """Return *value* only if it is in the *allowed* whitelist, else *default*."""
    return value if value in allowed else default


def compute_bot_session_ids(
    website_id: str,
    start_date: Any,
    end_date: Any,
    config: dict[str, Any],
) -> list[str]:
    """No-op: sessions are not tracked by the product."""
    return []


def build_bot_filter_sql(
    config: dict[str, Any],
    bot_session_ids: list[str] | None = None,
) -> dict[str, Any]:
    """No-op: sessions are not tracked by the product."""
    return {"where": "", "needs_session_join": False, "params": {}}


@dataclass
class Filter:
    column: str
    operator: str
    value: str


def build_filter_sql(filters: list[Filter]) -> dict[str, Any]:
    """Build SQL WHERE fragment and params from a list of :class:`Filter` objects.

    In the strict aggregate product, all filterable columns are on website_event directly.
    No session joins are needed.
    """
    params: dict[str, Any] = {}

    regular_filters: list[Filter] = []
    for f in filters:
        if f.column == "__bot_filter__":
            # Bot filtering is handled separately in aggregate mode
            continue
        elif f.column in VALID_FILTER_COLUMNS:
            regular_filters.append(f)

    grouped: dict[str, list[tuple[Filter, int]]] = {}
    for i, f in enumerate(regular_filters):
        grouped.setdefault(f.column, []).append((f, i))

    and_clauses: list[str] = []

    for entries in grouped.values():
        or_clauses: list[str] = []

        for f, index in entries:
            param_name = f"f{index}"
            prefix = "we"  # All columns are on website_event

            if f.operator == "eq":
                or_clauses.append(f"{prefix}.{f.column} = {{{{{param_name}}}}}")
                params[param_name] = f.value
            elif f.operator == "neq":
                or_clauses.append(f"{prefix}.{f.column} != {{{{{param_name}}}}}")
                params[param_name] = f.value
            elif f.operator == "contains":
                or_clauses.append(f"{prefix}.{f.column} ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"%{f.value}%"
            elif f.operator == "not_contains":
                or_clauses.append(f"{prefix}.{f.column} NOT ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"%{f.value}%"
            elif f.operator == "starts_with":
                or_clauses.append(f"{prefix}.{f.column} ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"{f.value}%"
            elif f.operator == "not_starts_with":
                or_clauses.append(f"{prefix}.{f.column} NOT ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"{f.value}%"

        if len(or_clauses) == 1:
            and_clauses.append(or_clauses[0])
        elif len(or_clauses) > 1:
            and_clauses.append(f"({' OR '.join(or_clauses)})")

    where = f"AND {' AND '.join(and_clauses)}" if and_clauses else ""
    return {
        "where": where,
        "params": params,
        "needs_session_join": False,
    }


def prepare_filters(filters: list[Filter] | None) -> tuple[str, dict[str, Any], str]:
    """Build the WHERE fragment, params, and session JOIN for an analytics query.

    Session joins are always empty because sessions are not tracked.
    """
    result = build_filter_sql(filters or [])
    # No session join needed because sessions are not tracked.
    session_join = ""
    return result["where"], result["params"], session_join


def parse_filters_from_params(filter_list: list[str]) -> list[Filter]:
    """Parse ``"column:operator:value"`` strings into :class:`Filter` objects."""
    result: list[Filter] = []
    for f in filter_list:
        first_colon = f.find(":")
        if first_colon == -1:
            continue
        column = f[:first_colon]
        rest = f[first_colon + 1 :]
        second_colon = rest.find(":")
        if second_colon == -1:
            continue
        operator = rest[:second_colon]
        value = rest[second_colon + 1 :]
        if not column or not operator or value is None:
            continue
        if column not in VALID_FILTER_COLUMNS:
            continue
        if operator not in VALID_OPERATORS:
            continue
        result.append(Filter(column=column, operator=operator, value=value))
    return result


def apply_filters(
    filters: list[Filter] | None = None,
    already_joins_session: bool = False,
) -> dict[str, Any]:
    """High-level helper: build filter SQL + optional JOIN clause."""
    if not filters:
        return {"where": "", "params": {}, "join": ""}
    result = build_filter_sql(filters)
    return {
        "where": result["where"],
        "params": result["params"],
        "join": "",
    }
