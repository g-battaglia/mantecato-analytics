"""Analytics query modules — read-only SQL via the Django/psycopg3 bridge.

Privacy-first aggregate-only mode: pageviews, custom-event names, device,
country, heatmap, realtime pageviews, and anonymous visitor estimates.

Active modules:
    stats           Aggregate pageview counts, time series, top pages, top sections, country breakdown.
    pageviews       Per-URL pageview metrics with pagination.
    realtime        Realtime aggregate pageviews and current pages.
    events          Custom-event counts by event name.
    devices         Browser, OS, device breakdowns (aggregate pageviews).
    geo             Country-level geographic breakdowns.
    heatmap         Traffic heatmap by day-of-week and hour.
    compare         Current vs previous period comparison (pageviews only).

"""

from core.mantecato_core.queries.compare import get_comparison_stats
from core.mantecato_core.queries.devices import get_device_metrics, get_device_metrics_multi
from core.mantecato_core.queries.events import get_event_metrics, get_event_time_series
from core.mantecato_core.queries.filter_values import get_filter_values
from core.mantecato_core.queries.geo import get_geo_metrics
from core.mantecato_core.queries.heatmap import get_traffic_heatmap
from core.mantecato_core.queries.pageviews import get_page_metrics, get_page_time_series
from core.mantecato_core.queries.realtime import (
    get_active_pageviews,
    get_current_pages,
    get_recent_pageviews,
)
from core.mantecato_core.queries.stats import (
    get_country_breakdown,
    get_first_event_date,
    get_pageview_time_series,
    get_pageview_time_series_comparison,
    get_top_pages,
    get_top_sections,
    get_website_stats,
    get_website_stats_comparison,
)
from core.mantecato_core.queries.visitors import (
    estimate_unique_visitors,
    estimate_unique_visitors_by_scope,
)

__all__ = [
    "get_active_pageviews",
    "estimate_unique_visitors",
    "estimate_unique_visitors_by_scope",
    "get_comparison_stats",
    "get_country_breakdown",
    "get_current_pages",
    "get_device_metrics",
    "get_device_metrics_multi",
    "get_filter_values",
    "get_event_metrics",
    "get_event_time_series",
    "get_first_event_date",
    "get_geo_metrics",
    "get_page_metrics",
    "get_page_time_series",
    "get_pageview_time_series",
    "get_pageview_time_series_comparison",
    "get_recent_pageviews",
    "get_top_pages",
    "get_top_sections",
    "get_traffic_heatmap",
    "get_website_stats",
    "get_website_stats_comparison",
]
