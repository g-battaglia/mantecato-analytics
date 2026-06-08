"""Analytics services — orchestrates read-only query calls for the dashboard.

Pageview aggregates plus **exact** site-level visitor/visit/bounce/duration
metrics from the cookieless compute-and-discard counter, and a referrer-**domain**
traffic-source breakdown. No full referrer URL, UTM, revenue, retention, funnel,
journey metrics, and no persistent per-person identifier. Unique visitors are
exact over the configured exactness window (``VISITOR_EXACT_WINDOW``, default
month); a range spanning several windows sums per-window uniques (no cross-window
linkage).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.mantecato_core.date_utils import (
    DateRange,
    get_comparison_range,
    resolve_granularity,
)

if TYPE_CHECKING:
    from core.mantecato_core.filters import Filter

from apps.analytics.formatting import (
    format_compact as _format_compact,
)
from apps.analytics.formatting import (
    percentage_change as _percentage_change,
)
from core.mantecato_core.helpers import format_duration
from core.mantecato_core.queries.devices import get_device_metrics_multi
from core.mantecato_core.queries.events import get_event_metrics, get_event_time_series
from core.mantecato_core.queries.geo import get_geo_metrics
from core.mantecato_core.queries.heatmap import get_traffic_heatmap
from core.mantecato_core.queries.pageviews import get_page_metrics
from core.mantecato_core.queries.realtime import (
    get_active_pageviews,
    get_current_pages,
    get_recent_pageviews,
)
from core.mantecato_core.queries.sources import get_referrer_metrics
from core.mantecato_core.queries.stats import (
    get_country_breakdown,
    get_pageview_time_series,
    get_pageview_time_series_comparison,
    get_top_pages,
    get_top_sections,
    get_website_stats_comparison,
)
from core.mantecato_core.queries.visitors import (
    get_landing_metrics,
    read_scope_visitors,
    visit_metrics,
)

_UNAVAILABLE_NOTE = "Unavailable with current filters"


def _stats_with_change(
    stats: dict[str, Any],
    prev_stats: dict[str, Any],
) -> dict[str, Any]:
    """Build the dashboard KPI cards.

    Pageview cards are always present. The visitor-derived cards (visitors,
    visits, bounce_rate, avg_duration, pages_per_visit) carry **exact** values
    when available and show ``N/A`` when suppressed (a content/device/geo filter
    narrows the population, which aggregate counts cannot represent). ``visitors``
    over a multi-day range is the sum of daily uniques.
    """

    def _change(cur: Any, prev: Any) -> Any:
        if cur is None or prev is None:
            return None
        return _percentage_change(cur, prev)

    def _pageview_card(key: str) -> dict[str, Any]:
        cur = stats.get(key) or 0
        return {"value": _format_compact(cur), "change": _change(cur, prev_stats.get(key) or 0)}

    def _exact_card(key: str, value: Any, *, note: str | None = None) -> dict[str, Any]:
        if stats.get(key) is None:
            return {"value": "N/A", "change": None, "unsupported": True, "note": _UNAVAILABLE_NOTE}
        change = _change(stats.get(key), prev_stats.get(key))
        return {"value": value, "change": change, "note": note}

    bounce = stats.get("bounce_rate")
    avg_duration = stats.get("avg_duration")
    ppv = stats.get("pages_per_visit")
    visitors = stats.get("visitors")
    visits = stats.get("visits")

    return {
        "pageviews": _pageview_card("pageviews"),
        "visitors": _exact_card(
            "visitors",
            _format_compact(visitors) if visitors is not None else "N/A",
        ),
        "visits": _exact_card("visits", _format_compact(visits) if visits is not None else "N/A"),
        "bounce_rate": _exact_card("bounce_rate", bounce),
        "avg_duration": _exact_card(
            "avg_duration",
            format_duration(avg_duration) if avg_duration is not None else "N/A",
        ),
        "pages_per_visit": _exact_card(
            "pages_per_visit",
            f"{ppv:.2f}" if ppv is not None else "N/A",
        ),
    }


def _add_percentage(
    rows: list[dict],
    value_key: str,
    target_key: str = "pct",
) -> None:
    """Mutate *rows* in place, adding a percentage-of-total field."""
    total = sum(r[value_key] for r in rows) if rows else 0
    for r in rows:
        r[target_key] = round(r[value_key] / total * 100, 1) if total else 0


def _attach_scope_visitors(
    website_id: str,
    start: Any,
    end: Any,
    rows: list[dict],
    *,
    scope: str,
    value_key: str,
    target_key: str = "visitors",
    filters: list[Filter] | None = None,
) -> None:
    """Attach **exact** per-scope (page/section/event) unique visitors to *rows*.

    Counts come from the per-event digests at read time, so the active **filters**
    (country/device/bot) slice them downstream — like the session-based product.
    Exact within the digest retention window.
    """
    if not rows:
        return
    values = [str(r.get(value_key) or "") for r in rows]
    counts = read_scope_visitors(
        website_id, start, end, scope=scope, scope_values=values, filters=filters
    )
    for row in rows:
        row[target_key] = counts.get(str(row.get(value_key) or ""))


def resolve_websites_for_user(user_id: str, is_admin: bool) -> list[dict[str, Any]]:
    """Return the websites the principal may access, alphabetically sorted."""
    from apps.core.models import Website

    qs = Website.objects.filter(is_deleted=False)
    if not is_admin:
        qs = qs.filter(user_id=user_id)
    return [{"id": str(w.id), "name": w.name, "domain": w.domain} for w in qs.order_by("name")]


def get_overview_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    *,
    granularity: str = "auto",
) -> dict[str, Any]:
    """Execute all read-only queries for the main overview/dashboard page.

    Returns pageview counts, exact visitor/visit/bounce KPIs, trends, top
    pages, top sections, device breakdowns, geo data, heatmap, and realtime
    counters.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    granularity = resolve_granularity(granularity, date_range)
    prev_range = get_comparison_range(date_range, "previous_period")

    stats_cmp = get_website_stats_comparison(
        website_id, start, end, prev_range.start_date, prev_range.end_date, filters
    )
    stats = _stats_with_change(stats_cmp["current"], stats_cmp["previous"])

    ts_cmp = get_pageview_time_series_comparison(
        website_id, start, end, prev_range.start_date, prev_range.end_date, granularity, filters
    )
    timeseries = ts_cmp["current"]
    prev_timeseries = ts_cmp["previous"]

    sections = get_top_sections(website_id, start, end, limit=10, filters=filters)
    _attach_scope_visitors(
        website_id,
        start,
        end,
        sections,
        scope="section",
        value_key="section",
        filters=filters,
    )
    _add_percentage(sections, "views")

    device_breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)

    country_data = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country_data, "pageviews")

    top_pages = get_top_pages(website_id, start, end, limit=10, filters=filters)
    _attach_scope_visitors(
        website_id,
        start,
        end,
        top_pages,
        scope="page",
        value_key="urlPath",
        filters=filters,
    )
    event_metrics = get_event_metrics(website_id, start, end, limit=10, filters=filters)
    _add_percentage(event_metrics, "count")
    _attach_scope_visitors(
        website_id,
        start,
        end,
        event_metrics,
        scope="event",
        value_key="eventName",
        filters=filters,
    )

    return {
        "stats": stats,
        "timeseries": timeseries,
        "prev_timeseries": prev_timeseries,
        "sections": sections,
        "top_pages": top_pages,
        "event_metrics": event_metrics,
        "browser": device_breakdown["browser"],
        "os_data": device_breakdown["os"],
        "device_data": device_breakdown["device"],
        "country": country_data,
        "geo": get_geo_metrics(website_id, start, end, limit=50, filters=filters),
        "realtime": get_active_pageviews(website_id, filters=filters),
        "recent_events": get_recent_pageviews(website_id, filters=filters),
        "current_pages": get_current_pages(website_id, filters=filters),
        "heatmap": get_traffic_heatmap(website_id, start, end, filters=filters),
        "date_range": date_range,
        "granularity": granularity,
    }


def get_pages_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Fetch paginated per-URL pageview metrics."""
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    offset = (page - 1) * 50

    pages = get_page_metrics(website_id, start, end, limit=50, offset=offset, filters=filters)
    _attach_scope_visitors(
        website_id,
        start,
        end,
        pages,
        scope="page",
        value_key="urlPath",
        filters=filters,
    )

    return {
        "pages": pages,
        "page": page,
    }


def get_sections_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch section-level analytics (URL-prefix groupings)."""
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    sections = get_top_sections(website_id, start, end, limit=100, filters=filters)
    _attach_scope_visitors(
        website_id,
        start,
        end,
        sections,
        scope="section",
        value_key="section",
        filters=filters,
    )
    _add_percentage(sections, "views")

    return {"sections": sections}


def get_heatmap_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Build a 7x24 traffic heatmap grid."""
    filters = filters or []
    rows = get_traffic_heatmap(
        website_id,
        date_range.start_date,
        date_range.end_date,
        filters=filters,
    )
    grid: list[list[int]] = [[0] * 24 for _ in range(7)]
    max_val = 0
    for r in rows:
        val = r["pageviews"]
        grid[r["dayOfWeek"]][r["hour"]] = val
        if val > max_val:
            max_val = val
    return {"grid": grid, "max_val": max_val}


def get_devices_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch all device-dimension breakdowns."""
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    breakdown = get_device_metrics_multi(website_id, start, end, limit=20, filters=filters)

    return {
        "browser": breakdown["browser"],
        "os": breakdown["os"],
        "device": breakdown["device"],
    }


def get_geo_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch geographic pageview breakdown (country-level only)."""
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    geo = get_geo_metrics(
        website_id,
        start,
        end,
        limit=50,
        filters=filters,
    )

    return {"geo": geo, "level": "country"}


def get_sources_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch the traffic-source breakdown (top referrer domains)."""
    filters = filters or []
    sources = get_referrer_metrics(
        website_id,
        date_range.start_date,
        date_range.end_date,
        limit=50,
        filters=filters,
    )
    return {"sources": sources}


def get_landing_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch entry (landing) pages with visits and engaged bounce rate."""
    filters = filters or []
    landing = get_landing_metrics(
        website_id,
        date_range.start_date,
        date_range.end_date,
        limit=50,
        filters=filters,
    )
    return {"landing": landing}


def get_compare_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    comparison_mode: str = "previous_period",
    *,
    granularity: str = "auto",
) -> dict[str, Any]:
    """Compute current-vs-previous period comparison for pageviews."""
    if comparison_mode not in ("previous_period", "previous_year"):
        comparison_mode = "previous_period"
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    comp_range = get_comparison_range(date_range, comparison_mode)

    from core.mantecato_core.queries.compare import get_comparison_stats
    comparison = get_comparison_stats(
        website_id,
        start,
        end,
        comp_range.start_date,
        comp_range.end_date,
        filters=filters,
    )

    current = next((r for r in comparison if r["period"] == "current"), None)
    previous = next((r for r in comparison if r["period"] == "previous"), None)

    if current and previous:
        cur_vm = visit_metrics(website_id, start, end, filters)
        prev_vm = visit_metrics(website_id, comp_range.start_date, comp_range.end_date, filters)
        # Surface exact metrics on the comparison rows for the per-period table.
        current |= cur_vm
        previous |= prev_vm
        stats = _stats_with_change(
            {
                "pageviews": current["pageviews"],
                "human_pageviews": current.get("human_pageviews", 0),
                "bot_pageviews": current.get("bot_pageviews", 0),
                **cur_vm,
            },
            {
                "pageviews": previous["pageviews"],
                "human_pageviews": previous.get("human_pageviews", 0),
                "bot_pageviews": previous.get("bot_pageviews", 0),
                **prev_vm,
            },
        )
    else:
        stats = _stats_with_change({"pageviews": 0}, {"pageviews": 0})

    granularity = resolve_granularity(granularity, date_range)
    current_ts = get_pageview_time_series(website_id, start, end, granularity, filters=filters)
    previous_ts = get_pageview_time_series(
        website_id,
        comp_range.start_date,
        comp_range.end_date,
        granularity,
        filters=filters,
    )

    return {
        "stats": stats,
        "comparison": comparison,
        "comparison_mode": comparison_mode,
        "current_ts": current_ts,
        "previous_ts": previous_ts,
    }


def get_events_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Fetch aggregate custom-event metrics."""
    website_id, date_range = args[0], args[1]
    filters = args[2] if len(args) > 2 else kwargs.get("filters")
    granularity = kwargs.get("granularity", "auto")
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    granularity = resolve_granularity(granularity, date_range)

    events = get_event_metrics(website_id, start, end, limit=50, filters=filters)
    _add_percentage(events, "count")
    _attach_scope_visitors(
        website_id,
        start,
        end,
        events,
        scope="event",
        value_key="eventName",
        filters=filters,
    )
    total = sum(e["count"] for e in events)
    top_names = [e["eventName"] for e in events[:5]]
    return {
        "events": events,
        "total_events": total,
        "event_types": len(events),
        "top_event": events[0]["eventName"] if events else "—",
        "event_timeseries": get_event_time_series(
            website_id,
            start,
            end,
            top_names,
            granularity,
            filters=filters,
        ),
    }

def get_overview_tab_pages(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch top-pages for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    pages = get_top_pages(website_id, start, end, limit=10, filters=filters)
    _attach_scope_visitors(
        website_id,
        start,
        end,
        pages,
        scope="page",
        value_key="urlPath",
        filters=filters,
    )
    return {"top_pages": pages}

def get_overview_tab_events(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch aggregate custom-event rows for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    events = get_event_metrics(website_id, start, end, limit=10, filters=filters)
    _add_percentage(events, "count")
    _attach_scope_visitors(
        website_id,
        start,
        end,
        events,
        scope="event",
        value_key="eventName",
        filters=filters,
    )
    return {"event_metrics": events}

def get_overview_tab_devices(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch device breakdowns for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)
    return {
        "browser": breakdown["browser"],
        "os_data": breakdown["os"],
        "device_data": breakdown["device"],
    }

def get_overview_tab_geo(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch geographic data for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    country = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country, "pageviews")
    return {
        "country": country,
        "geo": get_geo_metrics(website_id, start, end, limit=50, filters=filters),
    }

def get_realtime_data(website_id: str) -> dict[str, Any]:
    """Fetch realtime aggregate pageview data."""
    from django.utils import timezone
    now = timezone.now()
    from core.mantecato_core.date_utils import DateRange
    dr = DateRange(start_date=now.replace(hour=0, minute=0, second=0, microsecond=0), end_date=now)
    return get_overview_data(website_id, dr, granularity="hour")
