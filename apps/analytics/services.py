"""Analytics services — orchestrates read-only query calls for all analytics pages.

All queries are pure SELECT calls against the Umami database. Business logic
(resolving date ranges, computing change percentages) lives here. Views call
these services and pass result dicts to templates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.mantecato_core.date_utils import (
    DateRange,
    get_auto_granularity,
    get_comparison_range,
)

if TYPE_CHECKING:
    from core.mantecato_core.filters import Filter

from apps.analytics.chart_data import (
    build_bounce_page_chart_data,
    build_distribution_chart_data,
    build_event_timeseries_chart_data,
    build_revenue_event_chart_data,
    build_revenue_timeseries_chart_data,
    build_sankey_data,
)
from apps.analytics.formatting import (
    format_compact as _format_compact,
)
from apps.analytics.formatting import (
    format_duration as _format_duration,
)
from apps.analytics.formatting import (
    percentage_change as _percentage_change,
)
from core.mantecato_core.queries.compare import get_comparison_stats
from core.mantecato_core.queries.devices import get_device_metrics, get_device_metrics_multi
from core.mantecato_core.queries.engagement import (
    get_bounce_rate_by_page,
    get_bounce_rate_by_source,
    get_duration_by_page,
    get_duration_distribution,
    get_duration_percentiles,
    get_sessions_for_bucket,
)
from core.mantecato_core.queries.events import (
    get_event_metrics,
    get_event_properties,
    get_event_time_series,
    get_event_time_series_multi,
)
from core.mantecato_core.queries.funnels import get_funnel
from core.mantecato_core.queries.geo import get_geo_metrics
from core.mantecato_core.queries.heatmap import get_traffic_heatmap
from core.mantecato_core.queries.journeys import (
    get_journeys,
    get_section_conversions,
    get_section_journeys,
)
from core.mantecato_core.queries.pageviews import (
    get_next_pages,
    get_page_metrics,
    get_time_on_page_distribution,
)
from core.mantecato_core.queries.realtime import (
    get_active_visitors,
    get_current_pages,
    get_recent_events,
)
from core.mantecato_core.queries.retention import get_retention
from core.mantecato_core.queries.revenue import (
    get_revenue_by_country,
    get_revenue_by_event,
    get_revenue_summary,
    get_revenue_time_series,
)
from core.mantecato_core.queries.sessions import get_session_activity, get_session_list
from core.mantecato_core.queries.sources import (
    get_channel_metrics,
    get_click_id_metrics,
    get_hostname_metrics,
    get_referrer_metrics,
    get_utm_metrics,
)
from core.mantecato_core.queries.stats import (
    get_country_breakdown,
    get_pageview_time_series,
    get_pageview_time_series_comparison,
    get_top_events,
    get_top_pages,
    get_top_referrers,
    get_top_sections,
    get_website_stats_comparison,
)


def _stats_with_change(
    stats: dict[str, int],
    prev_stats: dict[str, int],
) -> dict[str, Any]:
    """Build a KPI card dict for each core metric.

    Pairs current values with period-over-period change.

    For every KPI the function computes a human-readable display value (via
    ``format_compact`` / ``format_duration``) **and** a percentage-change dict
    (``{"value": "12.3%", "trend": "up"|"down"|"flat"}``) that the stat-card
    template renders as a colored badge.

    Derived metrics (bounce_rate, avg_duration, pages_per_visit) are computed
    inline from the raw counters to avoid a second database round-trip.

    Args:
        stats: Raw counters for the **current** period.  Expected keys:
            ``pageviews``, ``visitors``, ``visits``, ``bounces``, ``totaltime``.
        prev_stats: Raw counters for the **comparison** period (same keys).

    Returns:
        A dict with keys ``pageviews``, ``visitors``, ``visits``,
        ``bounce_rate``, ``avg_duration``, ``pages_per_visit``.  Each value
        is itself a dict::

            {
                "value": <formatted display string or number>,
                "change": {"value": "<pct>%", "trend": "up"|"down"|"flat"} | None,
            }

        ``avg_duration`` also includes a ``raw_seconds`` int for sort/compare.
    """
    return {
        "pageviews": {
            "value": _format_compact(stats["pageviews"]),
            "change": _percentage_change(stats["pageviews"], prev_stats["pageviews"]),
        },
        "visitors": {
            "value": _format_compact(stats["visitors"]),
            "change": _percentage_change(stats["visitors"], prev_stats["visitors"]),
        },
        "visits": {
            "value": _format_compact(stats["visits"]),
            "change": _percentage_change(stats["visits"], prev_stats["visits"]),
        },
        "bounce_rate": {
            "value": (
                round(stats["bounces"] / stats["visits"] * 100, 1) if stats["visits"] > 0 else 0
            ),
            "change": _percentage_change(
                stats["bounces"] / stats["visits"] if stats["visits"] > 0 else 0,
                prev_stats["bounces"] / prev_stats["visits"] if prev_stats["visits"] > 0 else 0,
            ),
        },
        "avg_duration": {
            "value": (
                _format_duration(
                    int(stats["totaltime"] / stats["visits"]) if stats["visits"] > 0 else 0
                )
            ),
            "raw_seconds": (
                int(stats["totaltime"] / stats["visits"]) if stats["visits"] > 0 else 0
            ),
            "change": _percentage_change(
                stats["totaltime"] / stats["visits"] if stats["visits"] > 0 else 0,
                prev_stats["totaltime"] / prev_stats["visits"] if prev_stats["visits"] > 0 else 0,
            ),
        },
        "pages_per_visit": {
            "value": (round(stats["pageviews"] / stats["visits"], 1) if stats["visits"] > 0 else 0),
            "change": _percentage_change(
                stats["pageviews"] / stats["visits"] if stats["visits"] > 0 else 0,
                prev_stats["pageviews"] / prev_stats["visits"] if prev_stats["visits"] > 0 else 0,
            ),
        },
    }


def _add_percentage(
    rows: list[dict],
    value_key: str,
    target_key: str = "pct",
) -> None:
    """Mutate *rows* in place, adding a percentage-of-total field.

    Computes the sum of ``row[value_key]`` across all rows, then sets
    ``row[target_key]`` to the rounded percentage each row contributes.
    This is an **in-place mutation** -- the function returns ``None`` and the
    caller is expected to pass the same ``rows`` list to the template.

    Args:
        rows: List of metric dicts (e.g. sections, events, referrers).
        value_key: The dict key holding the numeric value to sum
            (e.g. ``"views"``, ``"visitors"``, ``"count"``).
        target_key: The dict key where the percentage will be written.
            Defaults to ``"pct"``.

    Returns:
        None -- rows are modified in place.  If the total is zero (empty
        dataset or all-zero values), every row gets ``0`` for ``target_key``.
    """
    total = sum(r[value_key] for r in rows) if rows else 0
    for r in rows:
        r[target_key] = round(r[value_key] / total * 100, 1) if total else 0


def resolve_websites_for_user(user_id: str, is_admin: bool) -> list[dict[str, Any]]:
    """Return the websites the principal may access, alphabetically sorted.

    Args:
        user_id: UUID string of the acting user. Ignored when *is_admin* is True.
        is_admin: ``True`` for admins (returns every non-deleted website),
            ``False`` for regular users (filters by ``user_id``).

    Returns:
        ``[{"id": str, "name": str, "domain": str | None}, ...]`` — the shape
        consumed by the website selector in templates and the JSON API.

    Cross-refs:
        - :class:`apps.common.mixins.WebsiteContextMixin`
        - :class:`apps.api.views.SitesListView`
    """
    from apps.core.models import Website

    qs = Website.objects.filter(is_deleted=False)
    if not is_admin:
        qs = qs.filter(user_id=user_id)
    return [{"id": str(w.id), "name": w.name, "domain": w.domain} for w in qs.order_by("name")]


def get_overview_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Execute all read-only queries needed by the main overview/dashboard page.

    This is the heaviest service call -- it fetches stats, time series, top
    pages/referrers/events, device breakdowns, geo data, channel metrics, and
    realtime counters in a single synchronous pass.  Each query is a SELECT
    against the analytics database via the mantecato-core query engine.

    The function also computes period-over-period change percentages by
    querying the comparison range (``get_comparison_range``) and feeding both
    periods through ``_stats_with_change``.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair for the current period.
        filters: Optional column-level filters (e.g. country, browser).

    Returns:
        A dict consumed by ``templates/analytics/overview.html`` with keys:

        - **stats** -- KPI cards dict from ``_stats_with_change``.
        - **timeseries** -- ``[{"time", "pageviews", "visitors"}, ...]``.
        - **sections** -- top URL-prefix groups with ``pct`` field added.
        - **top_pages** -- ``[{"urlPath", "pageTitle", "views", ...}, ...]``.
        - **top_referrers** -- with ``pct`` field added by ``_add_percentage``.
        - **top_events** -- ``[{"eventName", "count", "visitors"}, ...]``.
        - **browser / os / device / language** -- device-dimension breakdowns.
        - **country** -- country breakdown rows.
        - **geo** -- geo rows for the Leaflet choropleth map.
        - **channels** -- marketing channel attribution rows.
        - **referrer_metrics** -- referrer domain rows.
        - **realtime** -- active visitor count (last 5 min).
        - **recent_events** -- latest tracked events.
        - **current_pages** -- pages with active visitors right now.
        - **date_range** -- the original DateRange (for template date pickers).
        - **granularity** -- auto-detected time bucket (``hour``/``day``/``month``).
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    granularity = get_auto_granularity(date_range)
    prev_range = get_comparison_range(date_range, "previous_period")

    # Current + previous period in one round trip each (byte-identical to
    # two separate calls -- see get_*_comparison docstrings).
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

    top_referrers = get_top_referrers(website_id, start, end, limit=10, filters=filters)
    _add_percentage(top_referrers, "visitors")

    event_metrics = get_event_metrics(website_id, start, end, limit=20, filters=filters)
    _add_percentage(event_metrics, "count")

    # Browser / OS / device / language breakdowns share the same base
    # scan, so one merged call replaces four sequential round trips.
    device_breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)

    country_data = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country_data, "visitors")

    return {
        "stats": stats,
        "timeseries": timeseries,
        "prev_timeseries": prev_timeseries,
        "sections": sections,
        "top_pages": get_top_pages(website_id, start, end, limit=10, filters=filters),
        "top_referrers": top_referrers,
        "top_events": get_top_events(website_id, start, end, limit=10, filters=filters),
        "browser": device_breakdown["browser"],
        "os": device_breakdown["os"],
        "device": device_breakdown["device"],
        "language": device_breakdown["language"],
        "country": country_data,
        "geo": get_geo_metrics(website_id, start, end, level="country", limit=50, filters=filters),
        "channels": get_channel_metrics(website_id, start, end, filters=filters),
        "referrer_metrics": get_referrer_metrics(website_id, start, end, limit=10, filters=filters),
        "realtime": get_active_visitors(website_id),
        "recent_events": get_recent_events(website_id),
        "current_pages": get_current_pages(website_id),
        "heatmap": get_traffic_heatmap(website_id, start, end, filters=filters),
        "event_metrics": event_metrics,
        "date_range": date_range,
        "granularity": granularity,
    }


# ---------------------------------------------------------------------------
# Tab-specific fetchers for OverviewTabView (avoid running all 18 queries)
# ---------------------------------------------------------------------------


def get_overview_tab_pages(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch only the top-pages slice for the overview page's Pages tab.

    Called by ``OverviewTabView`` when the user switches to the Pages sub-tab
    via HTMX, avoiding the full 18-query ``get_overview_data`` round-trip.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"top_pages": [{"urlPath", "pageTitle", "views", ...}, ...]}``
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    return {"top_pages": get_top_pages(website_id, start, end, limit=10, filters=filters)}


def get_overview_tab_referrers(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch only the top-referrers slice for the overview page's Referrers tab.

    Adds a ``pct`` field to each referrer row via ``_add_percentage`` so the
    template can render percentage bars.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"top_referrers": [{"referrerDomain", "visitors", "pct"}, ...]}``
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    top_referrers = get_top_referrers(website_id, start, end, limit=10, filters=filters)
    _add_percentage(top_referrers, "visitors")
    return {"top_referrers": top_referrers}


def get_overview_tab_events(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch only the top-events slice for the overview page's Events tab.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"top_events": [{"eventName", "count", "visitors"}, ...]}``
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    return {"top_events": get_top_events(website_id, start, end, limit=10, filters=filters)}


def get_overview_tab_devices(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch device-dimension breakdowns for the overview page's Devices tab.

    Returns four device facets (browser, OS, device type, language), each
    limited to 10 entries, for the overview doughnut charts.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"browser": [...], "os_data": [...], "device_data": [...], "language": [...]}``
        Each list contains ``{"value": str, "visitors": int}`` dicts.
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    breakdown = get_device_metrics_multi(website_id, start, end, limit=10, filters=filters)
    return {
        "browser": breakdown["browser"],
        "os_data": breakdown["os"],
        "device_data": breakdown["device"],
        "language": breakdown["language"],
    }


def get_overview_tab_geo(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch geographic data for the overview page's Geo tab.

    Returns both a country-breakdown table (top 10) and geo-metric rows
    (top 50) used by the Leaflet choropleth map.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"country": [...], "geo": [...]}`` where ``country`` rows have
        ``{"country", "visitors"}`` and ``geo`` rows include lat/lng for mapping.
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    country = get_country_breakdown(website_id, start, end, limit=10, filters=filters)
    _add_percentage(country, "visitors")
    return {
        "country": country,
        "geo": get_geo_metrics(website_id, start, end, level="country", limit=50, filters=filters),
    }


def get_overview_tab_sources(
    website_id: str, date_range: DateRange, filters: list[Filter] | None = None
) -> dict[str, Any]:
    """Fetch traffic-source data for the overview page's Sources tab.

    Returns marketing channel attribution and referrer domain metrics for
    the Sources sub-tab on the overview page.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"channels": [{"channel", "visitors"}, ...], "referrer_metrics": [...]}``
    """
    filters = filters or []
    start, end = date_range.start_date, date_range.end_date
    return {
        "channels": get_channel_metrics(website_id, start, end, filters=filters),
        "referrer_metrics": get_referrer_metrics(website_id, start, end, limit=10, filters=filters),
    }


def get_pages_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Fetch paginated per-URL metrics for the Pages analytics page.

    Queries ``get_page_metrics`` which returns each tracked URL with its view
    count, unique visitors, average time-on-page, bounce rate, and entry/exit
    counts.  Results are paginated server-side (50 rows per page).

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters (e.g. browser, country).
        page: 1-based page number for pagination.  Each page returns up to
            50 rows; the offset is computed as ``(page - 1) * 50``.

    Returns:
        ``{"pages": [...], "page": <int>}`` where each page dict contains
        keys ``urlPath``, ``pageTitle``, ``views``, ``visitors``,
        ``avgDuration``, ``bounceRate``, ``entries``, ``exits``.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    offset = (page - 1) * 50

    pages = get_page_metrics(website_id, start, end, limit=50, offset=offset, filters=filters)

    return {
        "pages": pages,
        "page": page,
    }


def get_entry_exit_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Compute ranked entry and exit pages with percentage shares.

    Fetches the full page metrics (up to 50 URLs), then sorts by entry count
    and exit count independently.  Each list is capped at the top 20 pages.
    An ``entryPct`` or ``exitPct`` field is computed as the page's share of
    total entries/exits across the dataset.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"entry_pages": [...], "exit_pages": [...]}`` where each page dict
        is augmented with ``entryPct`` (float, 0-100) or ``exitPct`` (float,
        0-100) respectively.
    """
    filters = filters or []
    pages = get_page_metrics(
        website_id,
        date_range.start_date,
        date_range.end_date,
        limit=50,
        filters=filters,
    )
    total_entries = sum(p["entries"] for p in pages) or 1
    total_exits = sum(p["exits"] for p in pages) or 1
    entry_pages = sorted(pages, key=lambda p: p["entries"], reverse=True)[:20]
    exit_pages = sorted(pages, key=lambda p: p["exits"], reverse=True)[:20]
    for p in entry_pages:
        p["entryPct"] = round(p["entries"] / total_entries * 100, 1)
    for p in exit_pages:
        p["exitPct"] = round(p["exits"] / total_exits * 100, 1)
    return {"entry_pages": entry_pages, "exit_pages": exit_pages}


def get_heatmap_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Build a 7x24 traffic heatmap grid (day-of-week x hour-of-day).

    Queries ``get_traffic_heatmap`` which returns per-(dayOfWeek, hour) pageview
    counts, then maps those into a 7-row by 24-column nested list for the
    heatmap template.  Also tracks the maximum cell value so the template can
    normalize color intensities.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"grid": [[int, ...], ...], "max_val": int}`` where ``grid[dow][hour]``
        is the pageview count.  ``dow`` 0 = Monday, 6 = Sunday.
    """
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


def get_sections_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch section-level analytics (URL-prefix groupings).

    Sections group individual page URLs by their first path segment
    (e.g. ``/blog/post-1`` and ``/blog/post-2`` both fall under ``/blog``).
    This provides a higher-level view of site structure than per-page metrics.

    A ``pct`` field is added to each section row via ``_add_percentage``
    representing the section's share of total views.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"sections": [{"section", "views", "visitors", "pages", "pct"}, ...]}``
        Limited to 100 sections, ordered by views descending.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    sections = get_top_sections(website_id, start, end, limit=100, filters=filters)
    _add_percentage(sections, "views")

    return {
        "sections": sections,
    }


def get_sources_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch all traffic-source dimensions for the Sources analytics page.

    Runs seven independent queries covering the full acquisition picture:
    referrer domains, marketing channels, three UTM dimensions (source,
    medium, campaign), click IDs (gclid/fbclid/etc.), and hostnames.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        A dict with keys ``referrers``, ``channels``, ``utm_source``,
        ``utm_medium``, ``utm_campaign``, ``click_ids``, ``hostnames``.
        Each value is a list of metric dicts with ``visitors`` counts.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    return {
        "referrers": get_referrer_metrics(website_id, start, end, limit=50, filters=filters),
        "channels": get_channel_metrics(website_id, start, end, filters=filters),
        "utm_source": get_utm_metrics(
            website_id,
            start,
            end,
            group_by="utm_source",
            limit=50,
            filters=filters,
        ),
        "utm_medium": get_utm_metrics(
            website_id,
            start,
            end,
            group_by="utm_medium",
            limit=50,
            filters=filters,
        ),
        "utm_campaign": get_utm_metrics(
            website_id,
            start,
            end,
            group_by="utm_campaign",
            limit=50,
            filters=filters,
        ),
        "click_ids": get_click_id_metrics(website_id, start, end, filters=filters),
        "hostnames": get_hostname_metrics(website_id, start, end, limit=50, filters=filters),
    }


def get_events_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch custom-event analytics for the Events page.

    Retrieves all tracked event types with counts, unique visitors, and
    timestamps.  Also generates time-series data for the top 5 events
    (used by the multi-line Chart.js timeline).  A ``pct`` percentage field
    is added to each event row.

    Stat-card summary values (``total_events``, ``event_types``, ``top_event``)
    are computed from the event list to avoid extra queries.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        A dict with keys:

        - **events** -- full event list with ``pct`` added.
        - **total_events** -- sum of all event counts.
        - **event_types** -- number of distinct event names.
        - **top_event** -- name of the highest-count event, or ``"---"`` if none.
        - **event_timeseries** -- ``[{"name": str, "data": [...]}, ...]`` for
          the top 5 events, each ``data`` entry shaped as
          ``{"time": str, "count": int}``.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    events = get_event_metrics(website_id, start, end, limit=100, filters=filters)
    _add_percentage(events, "count")

    granularity = get_auto_granularity(date_range)
    # Fetch the top-5 event series in one query instead of a per-event loop.
    top_names = [ev["eventName"] for ev in events[:5]]
    ts_by_event = get_event_time_series_multi(
        website_id, top_names, start, end, granularity, filters=filters
    )
    event_timeseries: list[dict[str, Any]] = [
        {"name": name, "data": ts_by_event.get(name, [])} for name in top_names
    ]

    return {
        "events": events,
        "total_events": sum(e["count"] for e in events),
        "event_types": len(events),
        "top_event": events[0]["eventName"] if events else "—",
        "event_timeseries": event_timeseries,
    }


def get_sessions_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    page: int = 1,
) -> dict[str, Any]:
    """Fetch a paginated list of individual sessions for the Sessions page.

    Each session row includes device info (browser, OS), geographic location,
    session duration, and page-view count.  Pagination is 50 sessions per page,
    offset-based.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.
        page: 1-based page number.  The offset is ``(page - 1) * 50``.

    Returns:
        ``{"sessions": [...], "page": <int>}`` where each session dict
        contains keys like ``sessionId``, ``browser``, ``os``, ``device``,
        ``country``, ``duration``, ``pageviews``, ``createdAt``.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date
    offset = (page - 1) * 50

    sessions = get_session_list(
        website_id,
        start,
        end,
        limit=50,
        offset=offset,
        filters=filters,
    )

    return {
        "sessions": sessions,
        "page": page,
    }


def get_devices_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch all five device-dimension breakdowns for the Devices page.

    Runs five independent ``get_device_metrics`` queries, one per dimension:
    browser name, operating system, device type (desktop/mobile/tablet),
    screen resolution, and browser language.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        ``{"browser": [...], "os": [...], "device": [...], "screen": [...],
        "language": [...]}`` where each list contains up to 20
        ``{"value": str, "visitors": int}`` dicts.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    # Browser / OS / device / language share the same base scan, so a
    # single merged call replaces four sequential round trips.  Screen is
    # not part of the multi helper (the overview never queries it) and
    # stays as an independent call.
    breakdown = get_device_metrics_multi(website_id, start, end, limit=20, filters=filters)
    browser = breakdown["browser"]
    os_data = breakdown["os"]
    device = breakdown["device"]
    language = breakdown["language"]
    screen = get_device_metrics(website_id, start, end, "screen", limit=20, filters=filters)

    return {
        "browser": browser,
        "os": os_data,
        "device": device,
        "screen": screen,
        "language": language,
    }


def get_geo_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    country: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Fetch geographic visitor breakdown with drill-down support.

    Implements a three-level geographic hierarchy: country -> region -> city.
    The drill-down level is auto-detected from the provided filter parameters:

    - No ``country`` or ``region``: returns country-level data.
    - ``country`` provided: returns regions within that country.
    - Both ``country`` and ``region``: returns cities within that region.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.
        country: ISO 3166-1 alpha-2 country code to drill into (e.g. ``"US"``).
        region: Region/state name to drill into (requires ``country``).

    Returns:
        A dict with keys:

        - **geo** -- list of ``{"country"|"region"|"city", "visitors"}`` dicts.
        - **level** -- ``"country"``, ``"region"``, or ``"city"``.
        - **country** -- the country filter applied (or ``None``).
        - **region** -- the region filter applied (or ``None``).
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    if region and country:
        level = "city"
    elif country:
        level = "region"
    else:
        level = "country"

    geo = get_geo_metrics(
        website_id,
        start,
        end,
        level=level,
        country_filter=country,
        region_filter=region,
        limit=50,
        filters=filters,
    )
    _add_percentage(geo, "visitors")

    result: dict[str, Any] = {
        "geo": geo,
        "level": level,
        "country": country,
        "region": region,
    }

    if level == "country" and geo:
        country_breakdown = get_country_breakdown(
            website_id, start, end, limit=10, filters=filters,
        )
        _add_percentage(country_breakdown, "visitors")
        result["country_breakdown"] = country_breakdown

        total_visitors = sum(g["visitors"] for g in geo)
        top = geo[0]
        avg_bounce = sum(g["bounceRate"] for g in geo) / len(geo)
        avg_duration = sum(g["avgDuration"] for g in geo) / len(geo)
        result["geo_summary"] = {
            "total_countries": len(geo),
            "total_visitors": total_visitors,
            "top_country": top["country"],
            "top_country_visitors": top["visitors"],
            "top_country_pct": top.get("pct", 0),
            "avg_bounce_rate": round(avg_bounce, 1),
            "avg_duration": round(avg_duration),
        }

        top_regions = get_geo_metrics(
            website_id, start, end, level="region",
            country_filter=top["country"], limit=10, filters=filters,
        )
        result["top_regions"] = top_regions
        result["top_regions_country"] = top["country"]

    return result


def get_compare_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
    comparison_mode: str = "previous_period",
) -> dict[str, Any]:
    """Compute current-vs-previous period comparison for the Compare page.

    Fetches aggregate stats for both the current and comparison periods, then
    computes KPI cards with change percentages via ``_stats_with_change``.
    Also fetches time-series data for both periods so the template can render
    an overlaid line chart (current = solid, previous = dashed).

    The comparison period is computed by ``get_comparison_range`` using one of
    two modes: ``"previous_period"`` (same-length window immediately before) or
    ``"previous_year"`` (same dates one year earlier).

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair for the current period.
        filters: Optional column-level filters.
        comparison_mode: Either ``"previous_period"`` or ``"previous_year"``.
            Invalid values are silently replaced with ``"previous_period"``.

    Returns:
        A dict with keys:

        - **stats** -- KPI cards dict from ``_stats_with_change``.
        - **comparison** -- raw comparison rows from the query engine.
        - **comparison_mode** -- the effective mode used.
        - **current_ts** -- pageview time series for the current period.
        - **previous_ts** -- pageview time series for the comparison period.
    """
    if comparison_mode not in ("previous_period", "previous_year"):
        comparison_mode = "previous_period"
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    comp_range = get_comparison_range(date_range, comparison_mode)

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
        stats = _stats_with_change(current, previous)
    else:
        zero_stats = {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0}
        stats = _stats_with_change(zero_stats, zero_stats)

    granularity = get_auto_granularity(date_range)
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


def get_retention_data(
    website_id: str,
    date_range: DateRange,
    granularity: str = "week",
) -> dict[str, Any]:
    """Fetch cohort retention data for the Retention analysis page.

    Groups visitors into cohorts by their first-visit week or month, then
    computes what percentage of each cohort returned in subsequent periods.
    The result is a triangular retention matrix rendered as a heatmap table.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        granularity: Cohort bucket size -- ``"week"`` or ``"month"``.
            Invalid values are silently replaced with ``"week"``.

    Returns:
        ``{"cohorts": [...], "granularity": str}`` where each cohort dict
        contains ``{"cohort": "<date>", "visitors": int, "periods": [float, ...]}``.
        The ``periods`` list holds retention percentages for each subsequent
        time period (P0 = 100%, P1 = first return period, etc.).
    """
    if granularity not in ("week", "month"):
        granularity = "week"

    cohorts = get_retention(
        website_id,
        date_range.start_date,
        date_range.end_date,
        granularity=granularity,
    )

    return {
        "cohorts": cohorts,
        "granularity": granularity,
    }


def get_funnels_data(
    website_id: str,
    date_range: DateRange,
    steps: list[dict[str, str]] | None = None,
    window_minutes: int = 60,
) -> dict[str, Any]:
    """Fetch multi-step funnel conversion data for the Funnels page.

    Defines a sequence of URL or event steps and computes how many visitors
    progressed through each step within a configurable time window.  If no
    steps are provided, a default 3-step funnel (``/`` -> ``/pricing`` ->
    ``/signup``) is used as a demonstration.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        steps: Ordered list of funnel step dicts, each with
            ``{"type": "url"|"event", "value": "<path_or_event_name>"}``.
            Defaults to a demo funnel if ``None`` or empty.
        window_minutes: Maximum elapsed minutes between the first and last
            step for a session to count as completing the funnel.

    Returns:
        A dict with keys:

        - **funnel_steps** -- ``[{"label": str, "visitors": int, "dropoff": int,
          "rate": float}, ...]`` ordered by step position.
        - **steps_config** -- the step definitions used (for re-rendering the form).
    """
    if not steps:
        steps = [
            {"type": "url", "value": "/"},
            {"type": "url", "value": "/pricing"},
            {"type": "url", "value": "/signup"},
        ]

    funnel_steps = get_funnel(
        website_id,
        date_range.start_date,
        date_range.end_date,
        steps=steps,
        window_minutes=window_minutes,
    )

    return {
        "funnel_steps": funnel_steps,
        "steps_config": steps,
    }


def get_journeys_data(
    website_id: str,
    date_range: DateRange,
    path_length: int = 3,
    limit: int = 20,
    mode: str = "sections",
) -> dict[str, Any]:
    """Fetch user journey paths and build Sankey diagram data for the Journeys page.

    Retrieves the most common multi-step navigation paths through the site,
    then transforms them into a D3-sankey-compatible node/link structure via
    ``build_sankey_data``.  Also fetches cross-section conversion flows showing
    how traffic moves between site sections and triggers events.

    Supports two modes: ``"sections"`` groups paths by URL-prefix sections
    (e.g. /blog, /docs) for a high-level view, while ``"pages"`` uses full
    URL paths for granular analysis.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        path_length: Number of steps in each journey path (default 3).
        limit: Maximum number of journey paths to retrieve (default 20).
        mode: Either ``"sections"`` or ``"pages"``.  Invalid values default
            to ``"sections"``.

    Returns:
        A dict with keys:

        - **journeys** -- ``[{"path": [str, ...], "count": int}, ...]``.
        - **sankey** -- ``{"nodes": [...], "links": [...], "steps": int}``
          ready for the D3-sankey layout.
        - **mode** -- the effective mode used.
        - **conversions** -- cross-section conversion flow data.
    """
    if mode not in ("sections", "pages"):
        mode = "sections"
    if mode == "sections":
        journeys = get_section_journeys(
            website_id,
            date_range.start_date,
            date_range.end_date,
            path_length=path_length,
            limit=limit,
        )
    else:
        journeys = get_journeys(
            website_id,
            date_range.start_date,
            date_range.end_date,
            path_length=path_length,
            limit=limit,
        )

    sankey = build_sankey_data(journeys)

    conversions = get_section_conversions(
        website_id,
        date_range.start_date,
        date_range.end_date,
    )

    return {
        "journeys": journeys,
        "sankey": sankey,
        "mode": mode,
        "conversions": conversions,
    }


def get_revenue_data(
    website_id: str,
    date_range: DateRange,
) -> dict[str, Any]:
    """Fetch revenue analytics data for the Revenue page.

    Runs four revenue queries (summary totals, time series, by-event breakdown,
    by-country breakdown) and pre-builds the Chart.js payloads for the revenue
    line chart and event bar chart.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.

    Returns:
        A dict with keys:

        - **summary** -- ``{"totalRevenue", "transactionCount", "avgRevenue"}``.
        - **time_series** -- ``[{"time", "revenue"}, ...]``.
        - **by_event** -- ``[{"eventName", "revenue", "count"}, ...]``.
        - **by_country** -- ``[{"country", "revenue"}, ...]``.
        - **revenue_chart_data** -- pre-built Chart.js line payload.
        - **event_chart_data** -- pre-built Chart.js bar payload.
    """
    start = date_range.start_date
    end = date_range.end_date
    granularity = get_auto_granularity(date_range)

    summary = get_revenue_summary(website_id, start, end)
    time_series = get_revenue_time_series(website_id, start, end, granularity)
    by_event = get_revenue_by_event(website_id, start, end, limit=20)
    by_country = get_revenue_by_country(website_id, start, end, limit=20)

    revenue_chart = build_revenue_timeseries_chart_data(time_series)
    event_chart = build_revenue_event_chart_data(by_event)

    return {
        "summary": summary,
        "time_series": time_series,
        "by_event": by_event,
        "by_country": by_country,
        "revenue_chart_data": revenue_chart,
        "event_chart_data": event_chart,
    }


def get_engagement_data(
    website_id: str,
    date_range: DateRange,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch engagement metrics for the Engagement analytics page.

    Runs five engagement queries covering session duration distribution
    (histogram buckets), statistical percentiles (p50/p75/p90/p95), per-page
    average duration, per-page bounce rates, and per-referrer-source bounce
    rates.  Pre-builds Chart.js payloads for the distribution bar chart and
    bounce-rate-by-page chart.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        filters: Optional column-level filters.

    Returns:
        A dict with keys:

        - **distribution** -- ``[{"bucket": str, "visits": int}, ...]``.
        - **percentiles** -- ``{"p50", "p75", "p90", "p95"}`` in seconds.
        - **duration_by_page** -- ``[{"urlPath", "avgDuration"}, ...]``.
        - **bounce_by_page** -- ``[{"urlPath", "bounceRate"}, ...]``.
        - **bounce_by_source** -- ``[{"referrerDomain", "bounceRate"}, ...]``.
        - **distribution_chart_data** -- pre-built Chart.js bar payload.
        - **bounce_chart_data** -- pre-built Chart.js bar payload.
    """
    filters = filters or []
    start = date_range.start_date
    end = date_range.end_date

    distribution = get_duration_distribution(website_id, start, end, filters=filters)
    percentiles = get_duration_percentiles(website_id, start, end, filters=filters)
    duration_by_page = get_duration_by_page(website_id, start, end, limit=20, filters=filters)
    bounce_by_page = get_bounce_rate_by_page(website_id, start, end, limit=20, filters=filters)
    bounce_by_source = get_bounce_rate_by_source(website_id, start, end, limit=20, filters=filters)

    distribution_chart = build_distribution_chart_data(distribution)
    bounce_chart = build_bounce_page_chart_data(bounce_by_page)

    return {
        "distribution": distribution,
        "percentiles": percentiles,
        "duration_by_page": duration_by_page,
        "bounce_by_page": bounce_by_page,
        "bounce_by_source": bounce_by_source,
        "distribution_chart_data": distribution_chart,
        "bounce_chart_data": bounce_chart,
    }


# ---------------------------------------------------------------------------
# HTMX partial data fetchers
# ---------------------------------------------------------------------------


def get_next_pages_data(
    website_id: str,
    url_path: str,
    date_range: DateRange,
) -> dict[str, Any]:
    """Fetch the pages visitors navigate to after viewing a specific URL.

    Called via HTMX when the user clicks a "next pages" drill-down link in the
    Pages table.  Returns the outbound navigation flow from the given URL path,
    showing which pages visitors go to after viewing this page.

    Args:
        website_id: UUID string of the tracked website.
        url_path: The URL path to analyze outbound navigation from
            (e.g. ``"/blog/my-post"``).
        date_range: Resolved start/end date pair.

    Returns:
        ``{"pages": [{"urlPath": str, "count": int}, ...], "url_path": str}``
        where ``pages`` lists destination URLs sorted by visit count descending,
        and ``url_path`` echoes back the queried path for template rendering.
    """
    return {
        "pages": get_next_pages(
            website_id,
            url_path,
            date_range.start_date,
            date_range.end_date,
        ),
        "url_path": url_path,
    }


def get_session_activity_data(
    session_id: str,
    website_id: str,
) -> dict[str, Any]:
    """Fetch the chronological event timeline for a single visitor session.

    Called via HTMX when the user expands a session row in the Sessions table.
    Returns all tracked events (pageviews + custom events) within the session,
    ordered by timestamp, to reconstruct the visitor's journey.

    Args:
        session_id: UUID string of the session to inspect.
        website_id: UUID string of the tracked website (used for query scoping).

    Returns:
        ``{"events": [{"eventType", "urlPath", "eventName", "createdAt"}, ...]}``
        ordered chronologically within the session.
    """
    return {"events": get_session_activity(session_id, website_id)}


def get_event_properties_data(
    website_id: str,
    event_name: str,
    date_range: DateRange,
) -> dict[str, Any]:
    """Fetch property breakdowns and time-series data for a single event type.

    Called via HTMX when the user clicks an event name in the Events table to
    drill down.  Retrieves all custom properties (key-value pairs) attached to
    the event, and generates a time-series line chart showing event frequency
    over the date range.

    Args:
        website_id: UUID string of the tracked website.
        event_name: The custom event name to analyze (e.g. ``"signup_click"``).
        date_range: Resolved start/end date pair.

    Returns:
        A dict with keys:

        - **properties** -- ``[{"propertyName", "propertyValue", "count"}, ...]``
          showing how many times each property key-value pair was recorded.
        - **event_name** -- echoed back for template rendering.
        - **ts_data** -- pre-built Chart.js line payload from
          ``build_event_timeseries_chart_data``.
    """
    props = get_event_properties(
        website_id,
        event_name,
        date_range.start_date,
        date_range.end_date,
    )
    granularity = get_auto_granularity(date_range)
    ts = get_event_time_series(
        website_id,
        event_name,
        date_range.start_date,
        date_range.end_date,
        granularity,
    )
    return {
        "properties": props,
        "event_name": event_name,
        "ts_data": build_event_timeseries_chart_data(event_name, ts),
    }


def get_engagement_bucket_data(
    website_id: str,
    date_range: DateRange,
    bucket: str,
    filters: list[Filter] | None = None,
) -> dict[str, Any]:
    """Fetch sample sessions that fall within a specific duration bucket.

    Called via HTMX when the user clicks a bar in the engagement duration
    distribution chart.  Returns up to 10 sessions whose duration matches
    the selected bucket (e.g. ``"30-60s"``, ``"1-5m"``), allowing the user
    to inspect individual session details.

    Args:
        website_id: UUID string of the tracked website.
        date_range: Resolved start/end date pair.
        bucket: Duration bucket identifier string (e.g. ``"0-10s"``,
            ``"10-30s"``, ``"30-60s"``, ``"1-5m"``, ``"5m+"``).
        filters: Optional column-level filters.

    Returns:
        ``{"data": [<session dicts>], "bucket": str}`` where ``data``
        contains up to 10 session rows and ``bucket`` echoes back the
        queried bucket for template rendering.
    """
    return {
        "data": get_sessions_for_bucket(
            website_id,
            date_range.start_date,
            date_range.end_date,
            bucket=bucket,
            limit=10,
            filters=filters or [],
        ),
        "bucket": bucket,
    }


def get_time_on_page_data(
    website_id: str,
    url_path: str,
    date_range: DateRange,
) -> dict[str, Any]:
    """Fetch time-on-page duration distribution for a specific URL.

    Called via HTMX when the user clicks a page row to see how long visitors
    spend on that particular page.  Returns histogram buckets with counts and
    computed percentage shares (``pct`` field added in-place).

    Args:
        website_id: UUID string of the tracked website.
        url_path: The URL path to analyze (e.g. ``"/pricing"``).
        date_range: Resolved start/end date pair.

    Returns:
        ``{"distribution": [{"bucket": str, "count": int, "pct": float}, ...],
        "url_path": str}`` where ``pct`` is the percentage of total views
        that fall into each duration bucket.
    """
    dist = get_time_on_page_distribution(
        website_id,
        url_path,
        date_range.start_date,
        date_range.end_date,
    )
    total = sum(d["count"] for d in dist) or 1
    for d in dist:
        d["pct"] = round(d["count"] / total * 100, 1)
    return {"distribution": dist, "url_path": url_path}


def get_journey_section_detail_data(
    website_id: str,
    section: str,
    date_range: DateRange,
) -> dict[str, Any]:
    """Fetch the top individual pages within a site section prefix.

    Called via HTMX when the user clicks a section row in the Journeys page
    to drill down into which specific pages within that section are most visited.
    Applies a ``starts_with`` filter on ``url_path`` to scope results to the
    given section prefix.

    Args:
        website_id: UUID string of the tracked website.
        section: URL-path prefix identifying the section (e.g. ``"/blog"``).
        date_range: Resolved start/end date pair.

    Returns:
        ``{"pages": [{"urlPath", "pageTitle", "views", ...}, ...],
        "section": str}`` where ``pages`` contains up to 20 page rows
        matching the section prefix, and ``section`` echoes back the
        queried prefix for template rendering.
    """
    from core.mantecato_core.filters import Filter as _Filter

    return {
        "pages": get_top_pages(
            website_id,
            date_range.start_date,
            date_range.end_date,
            limit=20,
            filters=[_Filter(column="url_path", operator="starts_with", value=section)],
        ),
        "section": section,
    }


def get_realtime_data(website_id: str) -> dict[str, Any]:
    """Fetch realtime visitor data for the Realtime analytics widget.

    Queries three realtime metrics: the count of currently-active visitors
    (sessions with activity in the last 5 minutes), the most recent tracked
    events, and the pages with active visitors right now.  These queries bypass
    the date-range system since they always look at the live window.

    Args:
        website_id: UUID string of the tracked website.

    Returns:
        A dict with keys:

        - **active** -- integer count of visitors active in the last 5 minutes.
        - **recent_events** -- ``[{"eventType", "urlPath", "createdAt"}, ...]``.
        - **current_pages** -- ``[{"urlPath", "visitors"}, ...]``.
    """
    active = get_active_visitors(website_id)
    events = get_recent_events(website_id)
    pages = get_current_pages(website_id)

    return {
        "active": active,
        "recent_events": events,
        "current_pages": pages,
    }
