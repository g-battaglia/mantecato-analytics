"""Analytics query modules — read-only SQL via the Django/psycopg3 bridge.

Each module exposes sync functions that call
:func:`~core.mantecato_core.database.raw_query` with hand-written analytics
SQL (CTEs, window functions, percentiles) that the ORM cannot express cleanly.

    stats           Overview metrics, time series, top pages/referrers/events.
    pageviews       Page-level analytics with entry/exit/bounce metrics.
    filter_values   Distinct-value autocomplete for filter columns.
    devices         Browser, OS, device, screen, language breakdowns.
    geo             Country/region/city geographic breakdowns.
    sources         Referrers, UTM, channels, click IDs, hostnames.
    sessions        Session list and per-session activity replay.
    events          Custom event metrics, time series, properties.
    compare         Current vs previous period comparison.
    realtime        Active visitors, recent events, current pages.
    heatmap         Traffic heatmap by day-of-week and hour.
    retention       Cohort retention analysis.
    funnels         Multi-step funnel analysis.
    journeys        User journey paths.
    revenue         Revenue summary, time series, by event/country.
    engagement      Duration distribution, percentiles, bounce rate analysis.

Report-table CRUD (dashboards, saved views, annotations, API keys, bot config,
scheduled exports) lives in the app services and uses the Django ORM.
"""

from core.mantecato_core.queries.compare import get_comparison_stats
from core.mantecato_core.queries.devices import get_device_metrics
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
)
from core.mantecato_core.queries.filter_values import get_filter_values
from core.mantecato_core.queries.funnels import get_funnel
from core.mantecato_core.queries.geo import get_geo_metrics
from core.mantecato_core.queries.heatmap import get_traffic_heatmap
from core.mantecato_core.queries.journeys import get_journeys
from core.mantecato_core.queries.pageviews import (
    get_next_pages,
    get_page_metrics,
    get_page_referrers,
    get_page_time_series,
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
from core.mantecato_core.queries.sessions import (
    get_session_activity,
    get_session_list,
)
from core.mantecato_core.queries.sources import (
    get_channel_metrics,
    get_click_id_metrics,
    get_hostname_metrics,
    get_referrer_metrics,
    get_referrer_pages,
    get_utm_detail_metrics,
    get_utm_metrics,
)
from core.mantecato_core.queries.stats import (
    get_country_breakdown,
    get_first_event_date,
    get_pageview_time_series,
    get_top_events,
    get_top_events_with_properties,
    get_top_pages,
    get_top_referrers,
    get_top_sections,
    get_website_stats,
)

__all__ = [
    "get_active_visitors",
    "get_bounce_rate_by_page",
    "get_bounce_rate_by_source",
    "get_channel_metrics",
    "get_click_id_metrics",
    "get_comparison_stats",
    "get_country_breakdown",
    "get_current_pages",
    "get_device_metrics",
    "get_duration_by_page",
    "get_duration_distribution",
    "get_duration_percentiles",
    "get_event_metrics",
    "get_event_properties",
    "get_event_time_series",
    "get_filter_values",
    "get_first_event_date",
    "get_funnel",
    "get_geo_metrics",
    "get_hostname_metrics",
    "get_journeys",
    "get_next_pages",
    "get_page_metrics",
    "get_page_referrers",
    "get_page_time_series",
    "get_pageview_time_series",
    "get_recent_events",
    "get_referrer_metrics",
    "get_referrer_pages",
    "get_retention",
    "get_revenue_by_country",
    "get_revenue_by_event",
    "get_revenue_summary",
    "get_revenue_time_series",
    "get_session_activity",
    "get_session_list",
    "get_sessions_for_bucket",
    "get_time_on_page_distribution",
    "get_top_events",
    "get_top_events_with_properties",
    "get_top_pages",
    "get_top_referrers",
    "get_top_sections",
    "get_traffic_heatmap",
    "get_utm_detail_metrics",
    "get_utm_metrics",
    "get_website_stats",
]
