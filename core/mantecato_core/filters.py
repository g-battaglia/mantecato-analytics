"""SQL filter builder — privacy-first aggregate mode.

Filters operate directly on anonymous ``website_event`` rows. There are no
session joins, visitor identifiers, UTM fields, or fingerprints — only the
referrer **domain** is filterable (never a full referrer URL).
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
    "event_name",
    "referrer_domain",
}

VALID_OPERATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "not_starts_with",
    # Multi-value membership. Value is a comma-separated list (e.g. "IT,FR").
    "in",
    "not_in",
}

# Positive (inclusive) operators. Within one column these OR together
# ("/trial/ OR /pro/"); the negated operators instead AND ("exclude BOTH
# /admin/ AND /login/") — OR-ing negations would be a tautology. Both the raw
# SQL (build_filter_sql) and the ORM fallback (apply_filters_to_qs) honour this.
POSITIVE_OPERATORS = frozenset({"eq", "contains", "starts_with", "in"})

GRANULARITIES = ("minute", "hour", "day", "week", "month")

# Bot detection is event-level only. The tracker stores a coarse bot flag and
# reason, never the raw User-Agent or a stable client identifier.
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


def build_bot_filter_sql(
    config: dict[str, Any] | str,
) -> dict[str, Any]:
    """Build aggregate bot-exclusion SQL from a BotConfig payload.

    Only event-level bot reasons and country exclusions are supported because
    privacy-first mode does not collect engagement or fingerprinting signals.
    """
    payload: dict[str, Any]
    if isinstance(config, str):
        try:
            payload = json.loads(config)
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = dict(config)
    cfg = payload.get("config", payload)
    if not isinstance(cfg, dict):
        cfg = {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    reasons: list[str] = []
    if cfg.get("knownBots", True):
        reasons.append("known_bot_user_agent")
    if cfg.get("emptyUa", True):
        reasons.append("empty_user_agent")
    if cfg.get("datacenterIps", True):
        reasons.append("datacenter_ip")
    if reasons:
        clauses.append("(we.bot_reason IS NULL OR we.bot_reason <> ALL({{botReasons::text[]}}))")
        params["botReasons"] = reasons

    excluded_countries = [
        str(code).upper()
        for code in cfg.get("excludedCountries", [])
        if isinstance(code, str) and len(code) == 2
    ]
    if excluded_countries:
        clauses.append(
            "(we.country IS NULL OR we.country <> ALL({{botExcludedCountries::text[]}}))"
        )
        params["botExcludedCountries"] = excluded_countries

    return {
        "where": f"AND {' AND '.join(clauses)}" if clauses else "",
        "needs_session_join": False,
        "params": params,
    }


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
    bot_sql = {"where": "", "params": {}}
    for f in filters:
        if f.column == "__bot_filter__":
            bot_sql = build_bot_filter_sql(f.value)
        elif f.column in VALID_FILTER_COLUMNS:
            regular_filters.append(f)

    grouped: dict[str, list[tuple[Filter, int]]] = {}
    for i, f in enumerate(regular_filters):
        grouped.setdefault(f.column, []).append((f, i))

    and_clauses: list[str] = []

    for entries in grouped.values():
        # Positive (inclusive) clauses OR together; negated clauses AND together
        # (OR-ing negations would match everything). See POSITIVE_OPERATORS.
        pos_clauses: list[str] = []
        neg_clauses: list[str] = []

        for f, index in entries:
            param_name = f"f{index}"
            prefix = "we"  # All columns are on website_event
            bucket = pos_clauses if f.operator in POSITIVE_OPERATORS else neg_clauses

            if f.operator == "eq":
                bucket.append(f"{prefix}.{f.column} = {{{{{param_name}}}}}")
                params[param_name] = f.value
            elif f.operator == "neq":
                bucket.append(f"{prefix}.{f.column} != {{{{{param_name}}}}}")
                params[param_name] = f.value
            elif f.operator == "contains":
                bucket.append(f"{prefix}.{f.column} ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"%{f.value}%"
            elif f.operator == "not_contains":
                bucket.append(f"{prefix}.{f.column} NOT ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"%{f.value}%"
            elif f.operator == "starts_with":
                bucket.append(f"{prefix}.{f.column} ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"{f.value}%"
            elif f.operator == "not_starts_with":
                bucket.append(f"{prefix}.{f.column} NOT ILIKE {{{{{param_name}}}}}")
                params[param_name] = f"{f.value}%"
            elif f.operator in ("in", "not_in"):
                # Comma-separated multi-value membership, bound as a text[] param
                # (same {{name::type}} array pattern used by the bot filter).
                # Values are trimmed so "US, CA" works.
                values = [v.strip() for v in (f.value.split(",") if f.value else []) if v.strip()]
                if not values:
                    # Empty membership: `in ()` matches nothing (don't silently
                    # drop → match-all); `not_in ()` excludes nothing (no-op).
                    if f.operator == "in":
                        bucket.append("1 = 0")
                    continue
                if f.operator == "in":
                    bucket.append(f"{prefix}.{f.column} = ANY({{{{{param_name}::text[]}}}})")
                else:
                    bucket.append(
                        f"({prefix}.{f.column} IS NULL "
                        f"OR {prefix}.{f.column} <> ALL({{{{{param_name}::text[]}}}}))"
                    )
                params[param_name] = values

        # column clause = (pos1 OR pos2 …) AND neg1 AND neg2 …
        column_parts: list[str] = []
        if len(pos_clauses) == 1:
            column_parts.append(pos_clauses[0])
        elif len(pos_clauses) > 1:
            column_parts.append(f"({' OR '.join(pos_clauses)})")
        column_parts.extend(neg_clauses)

        if len(column_parts) == 1:
            and_clauses.append(column_parts[0])
        elif len(column_parts) > 1:
            and_clauses.append(f"({' AND '.join(column_parts)})")

    where = f"AND {' AND '.join(and_clauses)}" if and_clauses else ""
    if bot_sql.get("where"):
        where = f"{where} {bot_sql['where']}".strip()
        params.update(bot_sql.get("params", {}))
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
