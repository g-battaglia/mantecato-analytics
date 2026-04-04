from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SESSION_COLUMNS = [
    "browser",
    "os",
    "device",
    "screen",
    "language",
    "country",
    "region",
    "city",
]

VALID_FILTER_COLUMNS: set[str] = {
    "url_path",
    "page_title",
    "hostname",
    "referrer_domain",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "event_name",
    "tag",
    "browser",
    "os",
    "device",
    "country",
    "region",
    "city",
    "language",
    "screen",
}

VALID_OPERATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "not_starts_with",
}


@dataclass
class Filter:
    column: str
    operator: str
    value: str


def build_filter_sql(filters: list[Filter]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    needs_session_join = False

    grouped: dict[str, list[tuple[Filter, int]]] = {}
    for i, f in enumerate(filters):
        if f.column not in VALID_FILTER_COLUMNS:
            continue
        grouped.setdefault(f.column, []).append((f, i))

    and_clauses: list[str] = []

    for entries in grouped.values():
        or_clauses: list[str] = []

        for f, index in entries:
            param_name = f"f{index}"
            is_session_col = f.column in SESSION_COLUMNS

            if is_session_col:
                needs_session_join = True

            prefix = "s" if is_session_col else "we"

            if f.operator == "eq":
                or_clauses.append(
                    f"{prefix}.{f.column} = {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f.value
            elif f.operator == "neq":
                or_clauses.append(
                    f"{prefix}.{f.column} != {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f.value
            elif f.operator == "contains":
                or_clauses.append(
                    f"{prefix}.{f.column} ILIKE {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f"%{f.value}%"
            elif f.operator == "not_contains":
                or_clauses.append(
                    f"{prefix}.{f.column} NOT ILIKE {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f"%{f.value}%"
            elif f.operator == "starts_with":
                or_clauses.append(
                    f"{prefix}.{f.column} ILIKE {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f"{f.value}%"
            elif f.operator == "not_starts_with":
                or_clauses.append(
                    f"{prefix}.{f.column} NOT ILIKE {{{{param_name}}}}".replace(
                        "param_name", param_name
                    )
                )
                params[param_name] = f"{f.value}%"

        if len(or_clauses) == 1:
            and_clauses.append(or_clauses[0])
        elif len(or_clauses) > 1:
            and_clauses.append(f"({' OR '.join(or_clauses)})")

    where = f"AND {' AND '.join(and_clauses)}" if and_clauses else ""
    return {
        "where": where,
        "params": params,
        "needs_session_join": needs_session_join,
    }


def parse_filters_from_params(filter_list: list[str]) -> list[Filter]:
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
    if not filters:
        return {"where": "", "params": {}, "join": ""}
    result = build_filter_sql(filters)
    return {
        "where": result["where"],
        "params": result["params"],
        "join": (
            "JOIN session s ON s.session_id = we.session_id"
            if result["needs_session_join"] and not already_joins_session
            else ""
        ),
    }
