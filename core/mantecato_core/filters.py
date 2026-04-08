from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Known bot/crawler browser name patterns for SIMILAR TO matching
BOT_BROWSER_PATTERN = (
    "%(bot|crawler|spider|scraper|headless|phantom|selenium|puppeteer"
    "|wget|curl|python|go-http|java|libwww|fetcher|slurp"
    "|googlebot|bingbot|yandex|baidu|facebookexternalhit"
    "|twitterbot|linkedinbot|whatsapp|telegrambot|discordbot"
    "|applebot|semrush|ahrefs|mj12bot|dotbot|petalbot"
    "|bytespider|gptbot|claudebot|chatgpt|searchbot)%"
)

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


def build_bot_filter_sql(config: dict[str, Any]) -> dict[str, Any]:
    """Build SQL WHERE clauses from a bot detection config.

    Returns {"where": str, "needs_session_join": bool}.
    The clauses use the same parameter placeholders ({websiteId}, {startDate},
    {endDate}) that every query already binds — no extra params needed.
    """
    clauses: list[str] = []
    needs_session_join = False
    behavioral_having: list[str] = []

    # Session-attribute heuristics (simple WHERE on session table)
    if config.get("knownBots", True):
        clauses.append(
            f"NOT (LOWER(COALESCE(s.browser, '')) SIMILAR TO '{BOT_BROWSER_PATTERN}')"
        )
        needs_session_join = True

    if config.get("emptyUa", True):
        clauses.append(
            "NOT (COALESCE(s.browser, '') = '' AND COALESCE(s.os, '') = '')"
        )
        needs_session_join = True

    if config.get("missingScreen"):
        clauses.append("NOT (COALESCE(s.screen, '') = '')")
        needs_session_join = True

    if config.get("missingLanguage"):
        clauses.append("NOT (COALESCE(s.language, '') = '')")
        needs_session_join = True

    excluded = config.get("excludedCountries") or []
    if excluded:
        # Sanitize: only allow 2-letter country codes
        safe_codes = [
            c.upper() for c in excluded
            if isinstance(c, str) and len(c) == 2 and c.isalpha()
        ]
        if safe_codes:
            in_list = ", ".join(f"'{c}'" for c in safe_codes)
            clauses.append(f"s.country NOT IN ({in_list})")
            needs_session_join = True

    # ── Cluster-based bot detection ──
    # Identifies (country, device) groups with abnormally high single-page
    # bounce rates and high volume — the signature of bot farms that use
    # headless Chrome and rotate user-agents.  Only the bounced sessions
    # from those suspicious clusters are excluded.
    if config.get("clusterDetection", True):
        bounce_threshold = max(50, min(100, int(config.get("clusterBounceThreshold", 90))))
        min_cluster_size = max(10, min(500, int(config.get("clusterMinSize", 100))))
        clauses.append(
            "we.session_id NOT IN ("
            "SELECT bs.session_id FROM ("
            "  SELECT bwe.session_id, bs2.country, bs2.device"
            "  FROM website_event bwe"
            "  JOIN session bs2 ON bs2.session_id = bwe.session_id"
            "  WHERE bwe.website_id = {{websiteId::uuid}}"
            "  AND bwe.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}"
            "  AND bwe.event_type = 1"
            "  GROUP BY bwe.session_id, bs2.country, bs2.device"
            "  HAVING COUNT(*) = 1"
            "  AND EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) = 0"
            ") AS bs "
            "WHERE (bs.country, bs.device) IN ("
            "  SELECT ss.country, ss.device FROM ("
            "    SELECT bwe2.session_id, ss2.country, ss2.device,"
            "    COUNT(*) AS pv,"
            "    EXTRACT(EPOCH FROM (MAX(bwe2.created_at) - MIN(bwe2.created_at))) AS dur"
            "    FROM website_event bwe2"
            "    JOIN session ss2 ON ss2.session_id = bwe2.session_id"
            "    WHERE bwe2.website_id = {{websiteId::uuid}}"
            "    AND bwe2.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}}"
            "    AND bwe2.event_type = 1"
            "    GROUP BY bwe2.session_id, ss2.country, ss2.device"
            "  ) AS ss "
            "  GROUP BY ss.country, ss.device"
            f"  HAVING COUNT(*) >= {min_cluster_size}"
            f"  AND SUM(CASE WHEN ss.pv = 1 AND ss.dur = 0 THEN 1 ELSE 0 END)::float / COUNT(*)::float > {bounce_threshold / 100}"
            ")"
            ")"
        )
        needs_session_join = True

    # ── Simple behavioral heuristics ──
    behavioral_having: list[str] = []

    if config.get("zeroEngagement", False):
        min_dur = config.get("minDuration", 0)
        if min_dur > 0:
            behavioral_having.append(
                f"(COUNT(*) = 1 AND EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) < {int(min_dur)})"
            )
        else:
            behavioral_having.append(
                "(COUNT(*) = 1 AND EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) = 0)"
            )

    velocity = config.get("highVelocityThreshold", 60)
    if velocity and velocity > 0:
        behavioral_having.append(
            f"(COUNT(*) > {int(velocity)} AND EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) < 60)"
        )

    if behavioral_having:
        having_expr = " OR ".join(behavioral_having)
        clauses.append(
            "we.session_id NOT IN ("
            "SELECT bwe.session_id FROM website_event bwe "
            "WHERE bwe.website_id = {{websiteId::uuid}} "
            "AND bwe.created_at BETWEEN {{startDate::timestamptz}} AND {{endDate::timestamptz}} "
            "AND bwe.event_type = 1 "
            f"GROUP BY bwe.session_id HAVING {having_expr}"
            ")"
        )

    where = ""
    if clauses:
        where = "AND " + " AND ".join(clauses)

    return {"where": where, "needs_session_join": needs_session_join}


def build_filter_sql(filters: list[Filter]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    needs_session_join = False
    bot_where = ""

    # Extract bot filter sentinel before processing regular filters
    regular_filters: list[Filter] = []
    for f in filters:
        if f.column == "__bot_filter__":
            try:
                config = json.loads(f.value)
            except (json.JSONDecodeError, TypeError):
                config = {}
            bot_result = build_bot_filter_sql(config)
            bot_where = bot_result["where"]
            if bot_result["needs_session_join"]:
                needs_session_join = True
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

    regular_where = f"AND {' AND '.join(and_clauses)}" if and_clauses else ""
    where = f"{regular_where} {bot_where}".strip()
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
