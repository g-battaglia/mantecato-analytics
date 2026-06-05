"""SQL filter builder — ported from mantecato-core legacy.

The filter engine is unchanged from the asyncpg version.  All generated SQL
fragments use the ``{{name}}`` / ``{{name::type}}`` placeholder syntax that
:func:`~core.mantecato_core.database._substitute_params` converts to ``%s``
at execution time.

No async/await, no asyncpg imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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

# Time-bucket granularities accepted by the timeseries queries.  Shared so
# the whitelist lives in one place instead of being re-declared inline in
# every function that interpolates the granularity into a date_trunc().
GRANULARITIES = ("minute", "hour", "day", "week", "month")


def safe_identifier(value: str, allowed: tuple[str, ...], default: str) -> str:
    """Return *value* only if it is in the *allowed* whitelist, else *default*.

    Central choke point for the few places that interpolate an identifier
    (granularity, dimension, column) straight into a raw-SQL f-string,
    where bound parameters can't be used.  Keeping the membership check in
    one auditable helper makes it impossible for a new call site to forget
    the whitelist and open an injection seam.
    """
    return value if value in allowed else default


@dataclass
class Filter:
    column: str
    operator: str
    value: str


def _heavy_heuristics_active(config: dict[str, Any]) -> bool:
    """Return ``True`` when the config asks for any heuristic that needs
    a per-session aggregation over the full event range.

    These are the rules that, before the per-request pre-computation,
    used to emit a ``NOT EXISTS`` subquery on every analytics call:
    cluster detection, zero-engagement detection, and high-velocity
    detection.  When all three are off the bot filter only ever produces
    cheap row-level WHERE clauses and pre-computation is unnecessary.
    """
    if not config.get("enabled", False):
        return False
    if config.get("clusterDetection", False):
        return True
    if config.get("zeroEngagement", False):
        return True
    velocity = config.get("highVelocityThreshold", 0)
    return bool(velocity and int(velocity) > 0)


def compute_bot_session_ids(
    website_id: str,
    start_date: Any,
    end_date: Any,
    config: dict[str, Any],
) -> list[str]:
    """Return the session_ids classified as bots by the heavy heuristics.

    Runs the per-session aggregation (formerly nested inside a
    ``NOT EXISTS`` subquery on every analytics call) **once** so that
    downstream queries can exclude bot sessions with a cheap
    ``session_id <> ALL(:array)`` check.

    Args:
        website_id: UUID of the tracked site.
        start_date / end_date: inclusive analysis window, matching the
            range used by the surrounding analytics queries.
        config: the resolved bot-detection config.  Cheap clauses are
            ignored here -- only ``clusterDetection``, ``zeroEngagement``
            and ``highVelocityThreshold`` contribute to the result.

    Returns:
        A list of UUID strings.  Empty when ``enabled`` is False, when no
        heavy heuristic is active, or when no session matches.
    """
    if not _heavy_heuristics_active(config):
        return []

    from core.mantecato_core.database import raw_query

    use_cluster = bool(config.get("clusterDetection", False))
    bounce_threshold = max(50, min(100, int(config.get("clusterBounceThreshold", 90))))
    min_cluster_size = max(10, min(500, int(config.get("clusterMinSize", 100))))
    zero_engagement = bool(config.get("zeroEngagement", False))
    min_duration = int(config.get("minDuration", 0))
    velocity = int(config.get("highVelocityThreshold", 0))

    # Mirror the WHERE branches that ``build_bot_filter_sql`` used to emit
    # inside the NOT EXISTS so the precomputed set matches exactly.
    exclusion_parts: list[str] = []
    if use_cluster:
        exclusion_parts.append(
            f"(pv = 1 AND dur = 0 AND cluster_total >= {min_cluster_size}"
            f" AND cluster_bounces::float / NULLIF(cluster_total, 0)::float"
            f" > {bounce_threshold / 100})"
        )
    if zero_engagement:
        if min_duration > 0:
            exclusion_parts.append(f"(pv = 1 AND dur < {min_duration})")
        else:
            exclusion_parts.append("(pv = 1 AND dur = 0)")
    if velocity > 0:
        exclusion_parts.append(f"(pv > {velocity} AND dur < 60)")

    if not exclusion_parts:
        return []

    if use_cluster:
        # Cluster detection compares each session against peers sharing
        # its (country, device) bucket.  ``website_event`` already
        # denormalises both columns, so we can skip the session JOIN and
        # let the per-event index cover the aggregation directly.
        select_cols = "bwe.session_id, bwe.country, bwe.device"
        window_cols = (
            ", COUNT(*) OVER w AS cluster_total,"
            " SUM(CASE WHEN pv = 1 AND dur = 0 THEN 1 ELSE 0 END) OVER w AS cluster_bounces"
        )
        window_def = "WINDOW w AS (PARTITION BY country, device)"
    else:
        # Without cluster detection the velocity / zero-engagement rules
        # only look at per-session totals, so the window can go too.
        select_cols = "bwe.session_id"
        window_cols = ""
        window_def = ""

    combined = " OR ".join(exclusion_parts)
    sql = f"""
SELECT session_id FROM (
  SELECT session_id, pv, dur{window_cols}
  FROM (
    SELECT {select_cols},
      COUNT(*) AS pv,
      EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) AS dur
    FROM website_event bwe
    WHERE bwe.website_id = {{{{websiteId::uuid}}}}
      AND bwe.created_at BETWEEN {{{{startDate::timestamptz}}}} AND {{{{endDate::timestamptz}}}}
      AND bwe.event_type = 1
    GROUP BY {select_cols}
  ) per_session
  {window_def}
) ranked
WHERE {combined}
"""
    rows = raw_query(
        sql,
        {"websiteId": website_id, "startDate": start_date, "endDate": end_date},
    )
    return [str(row["session_id"]) for row in rows]


def build_bot_filter_sql(
    config: dict[str, Any],
    bot_session_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build SQL WHERE clauses from a bot detection config.

    Returns ``{"where": str, "needs_session_join": bool, "params": dict}``.
    The clauses use the same parameter placeholders (``{{websiteId}}``,
    ``{{startDate}}``, ``{{endDate}}``) that every query already binds.

    Honors ``config["enabled"]`` as a hard kill-switch: when missing or
    falsy this returns an empty result with no clauses, even if other
    keys are set.  This guards against accidental activation of the heavy
    cluster-detection subquery whenever the caller forgets to gate on
    ``enabled`` itself.

    When *bot_session_ids* is provided (computed once per request via
    :func:`compute_bot_session_ids`) the heavy heuristics emit a cheap
    ``session_id <> ALL(:array)`` check instead of re-running the
    per-session aggregation as a NOT EXISTS subquery for every analytics
    call.
    """
    if not config.get("enabled", False):
        return {"where": "", "needs_session_join": False, "params": {}}

    clauses: list[str] = []
    needs_session_join = False

    if config.get("knownBots", True):
        clauses.append("NOT (LOWER(COALESCE(s.browser, '')) SIMILAR TO {{__bot_pattern__}})")
        needs_session_join = True

    if config.get("emptyUa", True):
        clauses.append("NOT (COALESCE(s.browser, '') = '' AND COALESCE(s.os, '') = '')")
        needs_session_join = True

    if config.get("missingScreen"):
        clauses.append("NOT (COALESCE(s.screen, '') = '')")
        needs_session_join = True

    if config.get("missingLanguage"):
        clauses.append("NOT (COALESCE(s.language, '') = '')")
        needs_session_join = True

    excluded = config.get("excludedCountries") or []
    if excluded:
        safe_codes = [
            c.upper() for c in excluded if isinstance(c, str) and len(c) == 2 and c.isalpha()
        ]
        if safe_codes:
            in_list = ", ".join(f"'{c}'" for c in safe_codes)
            clauses.append(f"s.country NOT IN ({in_list})")
            needs_session_join = True

    # Heavy heuristics (cluster, zero-engagement, velocity) used to run as a
    # NOT EXISTS subquery embedded in every analytics call.  When the caller
    # provides a precomputed ``bot_session_ids`` list (typically via
    # :func:`compute_bot_session_ids`, executed once per request), swap that
    # subquery for a cheap ``session_id <> ALL(:array)`` check.  When no list
    # is provided we fall back to the legacy inline subquery so this function
    # stays usable in isolation (e.g. ad-hoc CLI scripts and tests).
    if _heavy_heuristics_active(config):
        if bot_session_ids is not None:
            # Pre-computed path: a Merge Anti Join on ``unnest(array)`` is
            # ~12x faster than ``<> ALL(array)`` once the bot list grows
            # past ~100 ids (the linear ``<> ALL`` scan becomes a
            # per-row hot spot).  An empty list means "no bots detected"
            # so we skip the clause entirely.
            if bot_session_ids:
                clauses.append(
                    "NOT EXISTS (SELECT 1 FROM unnest({{__bot_session_ids__::uuid[]}})"
                    " AS bots(session_id) WHERE bots.session_id = we.session_id)"
                )
        else:
            # Legacy fallback path -- one subquery per analytics call.
            use_cluster = bool(config.get("clusterDetection", False))
            exclusion_parts: list[str] = []

            if use_cluster:
                bounce_threshold = max(50, min(100, int(config.get("clusterBounceThreshold", 90))))
                min_cluster_size = max(10, min(500, int(config.get("clusterMinSize", 100))))
                exclusion_parts.append(
                    f"(ranked.pv = 1 AND ranked.dur = 0"
                    f" AND ranked.cluster_total >= {min_cluster_size}"
                    f" AND ranked.cluster_bounces::float"
                    f" / NULLIF(ranked.cluster_total, 0)::float > {bounce_threshold / 100})"
                )

            if config.get("zeroEngagement", False):
                min_dur = config.get("minDuration", 0)
                if min_dur > 0:
                    exclusion_parts.append(f"(ranked.pv = 1 AND ranked.dur < {int(min_dur)})")
                else:
                    exclusion_parts.append("(ranked.pv = 1 AND ranked.dur = 0)")

            velocity = config.get("highVelocityThreshold", 0)
            if velocity and velocity > 0:
                exclusion_parts.append(f"(ranked.pv > {int(velocity)} AND ranked.dur < 60)")

            if exclusion_parts:
                combined = " OR ".join(exclusion_parts)

                if use_cluster:
                    select_cols = "bwe.session_id, s_inner.country, s_inner.device"
                    join_clause = "JOIN session s_inner ON s_inner.session_id = bwe.session_id "
                    window_cols = (
                        ", COUNT(*) OVER w AS cluster_total"
                        ", SUM(CASE WHEN ss.pv = 1 AND ss.dur = 0"
                        " THEN 1 ELSE 0 END) OVER w AS cluster_bounces"
                    )
                    window_def = " WINDOW w AS (PARTITION BY ss.country, ss.device)"
                else:
                    select_cols = "bwe.session_id"
                    join_clause = ""
                    window_cols = ""
                    window_def = ""

                clauses.append(
                    "NOT EXISTS ("
                    "SELECT 1 FROM ("
                    "SELECT ss.session_id, ss.pv, ss.dur"
                    f"{window_cols} "
                    "FROM ("
                    f"SELECT {select_cols}, "
                    "COUNT(*) AS pv, "
                    "EXTRACT(EPOCH FROM (MAX(bwe.created_at) - MIN(bwe.created_at))) AS dur "
                    "FROM website_event bwe "
                    f"{join_clause}"
                    "WHERE bwe.website_id = {{websiteId::uuid}} "
                    "AND bwe.created_at BETWEEN {{startDate::timestamptz}} "
                    "AND {{endDate::timestamptz}} "
                    "AND bwe.event_type = 1 "
                    f"GROUP BY {select_cols}"
                    f") ss{window_def}"
                    ") ranked "
                    f"WHERE ranked.session_id = we.session_id AND ({combined})"
                    ")"
                )
                needs_session_join = True

    extra_params: dict[str, Any] = {}
    if config.get("knownBots", True):
        extra_params["__bot_pattern__"] = BOT_BROWSER_PATTERN
    if bot_session_ids:
        extra_params["__bot_session_ids__"] = bot_session_ids

    where = ""
    if clauses:
        where = "AND " + " AND ".join(clauses)

    return {"where": where, "needs_session_join": needs_session_join, "params": extra_params}


def build_filter_sql(filters: list[Filter]) -> dict[str, Any]:
    """Build SQL WHERE fragment and params from a list of :class:`Filter` objects."""
    params: dict[str, Any] = {}
    needs_session_join = False
    bot_where = ""

    regular_filters: list[Filter] = []
    for f in filters:
        if f.column == "__bot_filter__":
            # Accepts two payload shapes:
            #   1. ``{"config": {...}, "botSessionIds": [...]}`` -- the
            #      per-request pre-computed form built by ``FiltersMixin``.
            #   2. ``{...}`` -- a bare config dict (legacy / ad-hoc callers).
            #      In that case ``build_bot_filter_sql`` falls back to its
            #      inline NOT EXISTS subquery.
            try:
                payload = json.loads(f.value)
            except (json.JSONDecodeError, TypeError):
                payload = {}
            if isinstance(payload, dict) and "config" in payload:
                config = payload.get("config") or {}
                bot_session_ids = payload.get("botSessionIds") or None
            else:
                config = payload if isinstance(payload, dict) else {}
                bot_session_ids = None
            bot_result = build_bot_filter_sql(config, bot_session_ids=bot_session_ids)
            bot_where = bot_result["where"]
            params.update(bot_result.get("params", {}))
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

    regular_where = f"AND {' AND '.join(and_clauses)}" if and_clauses else ""
    where = f"{regular_where} {bot_where}".strip()
    return {
        "where": where,
        "params": params,
        "needs_session_join": needs_session_join,
    }


def prepare_filters(filters: list[Filter] | None) -> tuple[str, dict[str, Any], str]:
    """Build the WHERE fragment, params, and session JOIN for an analytics query.

    Bundles the boilerplate every analytics query repeats: returns
    ``(where, params, session_join)`` ready to interpolate into the SQL.
    """
    result = build_filter_sql(filters or [])
    session_join = (
        "JOIN session s ON s.session_id = we.session_id" if result["needs_session_join"] else ""
    )
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
        "join": (
            "JOIN session s ON s.session_id = we.session_id"
            if result["needs_session_join"] and not already_joins_session
            else ""
        ),
    }
