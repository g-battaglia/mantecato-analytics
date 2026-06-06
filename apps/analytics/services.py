"""Analytics services — orchestrates read-only query calls for aggregate pageview analytics.

The product supports only aggregate pageview metrics.
No visitor, session, bounce, time-on-site, referrer, UTM, event, revenue,
retention, funnel, journey, or engagement metrics.
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
from core.mantecato_core.queries.devices import get_device_metrics_multi
from core.mantecato_core.queries.geo import get_geo_metrics
from core.mantecato_core.queries.heatmap import get_traffic_heatmap
from core.mantecato_core.queries.pageviews import get_page_metrics
from core.mantecato_core.queries.realtime import (
    get_active_pageviews,
    get_current_pages,
    get_recent_pageviews,
)
from core.mantecato_core.queries.stats import (
    get_country_breakdown,
    get_pageview_time_series,
    get_pageview_time_series_comparison,
    get_top_pages,
    get_top_sections,
    get_website_stats_comparison,
)


def _stats_with_change(
    stats: dict[str, int],
    prev_stats: dict[str, int],
) -> dict[str, Any]:
    """Build a KPI card dict for pageviews with period-over-period change."""
    return {
        "pageviews": {
            "value": _format_compact(stats["pageviews"]),
            "change": _percentage_change(stats["pageviews"], prev_stats["pageviews"]),
        },
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

    In the strict aggregate product, this returns pageview counts, trends,
    top pages, top sections, device breakdowns, geo data, heatmap, and
    realtime counters.
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
    _add_percentage(sections, "views")

    device_breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)

    country_data = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country_data, "pageviews")

    return {
        "stats": stats,
        "timeseries": timeseries,
        "prev_timeseries": prev_timeseries,
        "sections": sections,
        "top_pages": get_top_pages(website_id, start, end, limit=10, filters=filters),
        "browser": device_breakdown["browser"],
        "os_data": device_breakdown["os"],
        "device_data": device_breakdown["device"],
        "country": country_data,
        "geo": get_geo_metrics(website_id, start, end, level="country", limit=50, filters=filters),
        "realtime": get_active_pageviews(website_id),
        "recent_events": get_recent_pageviews(website_id),
        "current_pages": get_current_pages(website_id),
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
        stats = _stats_with_change(
            {"pageviews": current["pageviews"]},
            {"pageviews": previous["pageviews"]},
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


# ---------------------------------------------------------------------------
# Backward-compatible aliases for removed service functions
# These return empty data to avoid import errors in tests or other modules.
# ---------------------------------------------------------------------------

def get_sessions_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"sessions": [], "page": 1}

def get_events_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"events": [], "total_events": 0, "event_types": 0, "top_event": "—", "event_timeseries": []}

def get_sources_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"referrers": [], "channels": [], "utm_source": [], "utm_medium": [], "utm_campaign": [], "click_ids": [], "hostnames": []}

def get_retention_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"cohorts": [], "granularity": "week"}

def get_funnels_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"funnel_steps": [], "steps_config": []}

def get_journeys_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"journeys": [], "sankey": {"nodes": [], "links": [], "steps": 0}, "mode": "sections", "conversions": []}

def get_revenue_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"summary": {}, "time_series": [], "by_event": [], "by_country": []}

def get_engagement_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"distribution": [], "percentiles": {}, "duration_by_page": [], "bounce_by_page": [], "bounce_by_source": []}

def get_entry_exit_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"entry_pages": [], "exit_pages": []}

def get_next_pages_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"pages": [], "url_path": ""}

def get_session_activity_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"events": []}

def get_event_properties_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"properties": [], "event_name": "", "ts_data": {}}

def get_engagement_bucket_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"data": [], "bucket": ""}

def get_time_on_page_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"data": []}

def get_overview_tab_pages(website_id: str, date_range: DateRange, filters: list[Filter] | None = None) -> dict[str, Any]:
    """Fetch top-pages for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    return {"top_pages": get_top_pages(website_id, start, end, limit=10, filters=filters)}

def get_overview_tab_referrers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"top_referrers": []}

def get_overview_tab_events(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"top_events": []}

def get_overview_tab_devices(website_id: str, date_range: DateRange, filters: list[Filter] | None = None) -> dict[str, Any]:
    """Fetch device breakdowns for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)
    return {
        "browser": breakdown["browser"],
        "os_data": breakdown["os"],
        "device_data": breakdown["device"],
    }

def get_overview_tab_geo(website_id: str, date_range: DateRange, filters: list[Filter] | None = None) -> dict[str, Any]:
    """Fetch geographic data for the overview tab."""
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    country = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country, "pageviews")
    return {
        "country": country,
        "geo": get_geo_metrics(website_id, start, end, level="country", limit=50, filters=filters),
    }

def get_overview_tab_sources(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Not supported by the product."""
    return {"channels": [], "referrer_metrics": []}


def get_realtime_data(website_id: str) -> dict[str, Any]:
    """Fetch realtime aggregate pageview data."""
    from django.utils import timezone
    now = timezone.now()
    from core.mantecato_core.date_utils import DateRange
    dr = DateRange(start_date=now.replace(hour=0, minute=0, second=0, microsecond=0), end_date=now)
    return get_overview_data(website_id, dr, granularity="hour")
