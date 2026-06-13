"""Shared helper functions for CLI, MCP, and other consumers of mantecato-core.

Ported from legacy with async removed.  All DB access goes through the sync
:func:`~core.mantecato_core.database.raw_query` bridge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .database import raw_query
from .date_utils import DateRange, resolve_date_range, resolve_granularity
from .filters import Filter, parse_filters_from_params


def list_sites() -> list[dict[str, Any]]:
    """Return all non-deleted websites."""
    rows = raw_query("SELECT id, name, domain FROM website WHERE is_deleted = false ORDER BY name")
    return [{"website_id": str(r["id"]), "name": r["name"], "domain": r["domain"]} for r in rows]


def resolve_site_id(site: str) -> str:
    """Resolve a site name, domain, or UUID to a website UUID string."""
    sites = list_sites()

    needle = site.lower()
    for s in sites:
        if needle in (
            s["website_id"].lower(),
            (s["name"] or "").lower(),
            (s["domain"] or "").lower(),
        ):
            return s["website_id"]

    # Substring fallback: only resolve when it is unambiguous. Matching the first
    # of several candidates would silently pick the wrong site (e.g. "shop"
    # matching both "shop.example.com" and "oldshop.example.com").
    matches = [
        s
        for s in sites
        if needle in (s["name"] or "").lower() or needle in (s["domain"] or "").lower()
    ]
    if len(matches) == 1:
        return matches[0]["website_id"]

    available = ", ".join(f"{s['name']} ({s['domain']})" for s in sites)
    if len(matches) > 1:
        ambiguous = ", ".join(f"{s['name']} ({s['domain']})" for s in matches)
        raise SystemExit(f"Ambiguous site '{site}' matches: {ambiguous}")
    raise SystemExit(f"Site not found: {site}\nAvailable sites: {available}")


def parse_date_args(
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> DateRange:
    """Resolve CLI-style date arguments to a :class:`DateRange`.

    Args:
        period: Range preset name (``"7d"``, ``"30d"``, …); only used when
            *start* is empty.
        start: ISO-8601 datetime string (lower bound, UTC).
        end: ISO-8601 datetime string (upper bound, UTC). When omitted but
            *start* is set, the range ends at "now".

    Returns:
        A populated :class:`DateRange`. Falls back to "last 365 days" when
        *period* is invalid (``"all"`` / ``"custom"`` / unknown preset).
    """
    if start and end:
        return DateRange(
            datetime.fromisoformat(start).replace(tzinfo=UTC),
            datetime.fromisoformat(end).replace(tzinfo=UTC),
        )
    if start:
        return DateRange(
            datetime.fromisoformat(start).replace(tzinfo=UTC),
            datetime.now(UTC),
        )

    preset = period or "30d"
    range_ = resolve_date_range(preset)
    if range_ is None:
        range_ = DateRange(
            datetime.now(UTC) - timedelta(days=365),
            datetime.now(UTC),
        )
    return range_


def parse_filter_args(filter_strs: list[str]) -> list[Filter]:
    """Parse a list of CLI ``--filter`` strings into :class:`Filter` objects."""
    if not filter_strs:
        return []
    return parse_filters_from_params(filter_strs)


def resolve_granularity_arg(granularity: str, range_: DateRange) -> str:
    """Thin alias around :func:`resolve_granularity` to keep the CLI surface stable."""
    return resolve_granularity(granularity, range_)


def compute_derived_stats(raw: dict[str, Any]) -> dict[str, Any]:
    """Overlay derived metrics (``bounce_rate``, ``avg_duration``, ``pages_per_visit``).

    Takes the raw aggregate dict returned by
    :func:`core.mantecato_core.queries.stats.get_website_stats` and adds the
    three ratios the CLI/MCP front-ends expect. The original keys are
    preserved untouched.
    """
    pageviews = raw.get("pageviews", 0) or 0
    _visitors = raw.get("visitors", 0) or 0
    visits = raw.get("visits", 0) or 0
    bounces = raw.get("bounces", 0) or 0
    total_duration = raw.get("totaltime", 0) or 0

    bounce_rate = (bounces / visits * 100) if visits > 0 else 0
    avg_duration = total_duration / visits if visits > 0 else 0
    pages_per_visit = pageviews / visits if visits > 0 else 0

    return {
        **raw,
        "bounce_rate": round(bounce_rate, 1),
        "avg_duration": round(avg_duration, 1),
        "pages_per_visit": round(pages_per_visit, 2),
    }


def num(n: int | float | None) -> str:
    """Render a number with thousands separators (or ``"-"`` for ``None``)."""
    if n is None:
        return "-"
    return f"{int(n):,}"


def pct_change(current: float | int | None, previous: float | int | None) -> str:
    """Render a signed percentage change (``"+12.3%"`` / ``"-7.1%"`` / ``"+New"`` / ``"-"``)."""
    if current is None or previous is None or previous == 0:
        if current is not None and previous == 0 and current > 0:
            return "+New"
        return "-"
    change = ((current - previous) / previous) * 100
    if change >= 0:
        return f"+{change:.1f}%"
    return f"{change:.1f}%"


def format_duration(seconds: float | None) -> str:
    """Render a number of seconds as ``Hh Mm`` / ``Mm Ss`` / ``Ss`` (CLI variant)."""
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
    """Render a float as ``"<n>%"`` (or ``"-"`` when value is ``None``)."""
    if value is None:
        return "-"
    return f"{value:.1f}%"
