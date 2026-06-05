"""Analytics page views — full-page endpoints for all analytics sections.

Each class maps to one user-navigable analytics page.  The architecture
uses **composition over inheritance**: five independent mixins each add
one concern (auth, website, dates, filters, base context), and the
:class:`~apps.analytics.view_utils.AnalyticsBase` Template Method wires
them together.

Chart data assembly is handled declaratively via ``_charts`` mappings
(see :class:`~apps.analytics.view_utils.ChartMapping`), keeping views
thin — most are 4–8 lines of class attributes plus a ``_call_service``
override.

HTMX partial fragments live in :mod:`apps.analytics.partials`.

Service functions are imported at module level so that existing tests can
patch ``apps.analytics.views.<fn>`` without touching the service module.
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.analytics.chart_data import (
    build_bounce_by_source_chart_data,
    build_channels_doughnut_data,
    build_comparison_chart_data,
    build_conversion_chart_data,
    build_dimension_chart_data,
    build_duration_by_page_chart_data,
    build_entry_exit_chart_data,
    build_events_bar_chart_data,
    build_events_pie_chart_data,
    build_events_timeline_data,
    build_funnel_chart_data,
    build_generic_pie_data,
    build_geo_bubble_data,
    build_geo_duration_bar_data,
    build_geo_regions_bar_data,
    build_pages_bar_chart_data,
    build_referrers_bar_chart_data,
    build_retention_curve_data,
    build_revenue_country_chart_data,
    build_sections_bar_chart_data,
    build_session_duration_chart_data,
    build_timeseries_chart_data,
    build_utm_bar_chart_data,
)
from apps.analytics.services import (
    get_compare_data,
    get_devices_data,
    get_engagement_data,
    get_entry_exit_data,
    get_events_data,
    get_funnels_data,
    get_geo_data,
    get_heatmap_data,
    get_journeys_data,
    get_overview_data,
    get_pages_data,
    get_realtime_data,
    get_retention_data,
    get_revenue_data,
    get_sections_data,
    get_sessions_data,
    get_sources_data,
    resolve_websites_for_user,  # noqa: F401 — test patch target
)
from apps.analytics.view_utils import AnalyticsBase, ChartMapping, build_chart_context
from apps.common.funnel_params import parse_funnel_steps
from apps.common.http import safe_int
from apps.common.mixins import (
    BaseContextMixin,
    DateRangeMixin,
    FiltersMixin,
    WebsiteContextMixin,
)

# ============================================================================
# Overview — main landing page, heaviest context assembly
# ============================================================================


class OverviewView(AnalyticsBase):
    """Default analytics landing page with stat cards, charts, and HTMX tabs.

    Assembles 15+ data sections from a single ``get_overview_data`` call
    and adds a Chart.js timeseries payload.  Sub-tab content is loaded via
    HTMX from :class:`~apps.analytics.partials.OverviewTabView`.
    """

    template_name = "analytics/overview.html"

    def get_service_data(self) -> dict:
        data = get_overview_data(self.website_id, self.date_range, self.filters)
        return {
            "stats": data["stats"],
            "timeseries_data": build_timeseries_chart_data(
                data["timeseries"], data["prev_timeseries"]
            ),
            "sections": data["sections"],
            "top_pages": data["top_pages"],
            "top_referrers": data["top_referrers"],
            "top_events": data["top_events"],
            "browser": data["browser"],
            "os_data": data["os"],
            "device_data": data["device"],
            "language": data["language"],
            "country": data["country"],
            "geo": data["geo"],
            "channels": data["channels"],
            "referrer_metrics": data["referrer_metrics"],
            "realtime": data["realtime"],
            "recent_events": data["recent_events"],
            "current_pages": data["current_pages"],
            "heatmap": data["heatmap"],
            "event_metrics": data["event_metrics"],
            "active_tab": self.request.GET.get("tab", "pages"),
        }


# ============================================================================
# Standard pages — declarative _charts + _call_service
# ============================================================================


class PagesView(AnalyticsBase):
    """Per-URL analytics: views, visitors, duration, bounce rate."""

    template_name = "analytics/pages.html"
    _charts = [ChartMapping("pages_chart_data", build_pages_bar_chart_data, "pages")]

    def _call_service(self) -> dict:
        page = safe_int(self.request.GET.get("page"))
        return get_pages_data(self.website_id, self.date_range, self.filters, page=page)


class SectionsView(AnalyticsBase):
    """Site sections breakdown by URL prefix."""

    template_name = "analytics/sections.html"
    _charts = [ChartMapping("sections_chart_data", build_sections_bar_chart_data, "sections")]

    def _call_service(self) -> dict:
        return get_sections_data(self.website_id, self.date_range, self.filters)


class SourcesView(AnalyticsBase):
    """Traffic source breakdown: referrers, UTM params, channels, click IDs."""

    template_name = "analytics/sources.html"

    def get_service_data(self) -> dict:
        data = get_sources_data(self.website_id, self.date_range, self.filters)
        return build_chart_context(
            data,
            [
                ChartMapping("channels_chart_data", build_channels_doughnut_data, "channels"),
                ChartMapping("referrers_chart_data", build_referrers_bar_chart_data, "referrers"),
                ChartMapping("utm_chart_data", build_utm_bar_chart_data, "utm_source"),
            ],
        ) | {
            # build_generic_pie_data takes extra args (label_key, value_key),
            # so it doesn't fit the standard ChartMapping single-key pattern
            "clickids_chart_data": build_generic_pie_data(
                data.get("click_ids", []),
                "platform",
                "visitors",
            ),
            "hostnames_chart_data": build_generic_pie_data(
                data.get("hostnames", []),
                "hostname",
                "visitors",
            ),
        }


class EventsView(AnalyticsBase):
    """Custom event analytics: counts, visitors, trend timelines."""

    template_name = "analytics/events.html"

    def get_service_data(self) -> dict:
        data = get_events_data(self.website_id, self.date_range, self.filters)
        # Events list is reused by three chart builders, so extract once
        events = data.get("events", [])
        return {
            "events_chart_data": build_events_bar_chart_data(events),
            "events_pie_data": build_events_pie_chart_data(events),
            "events_timeline_data": build_events_timeline_data(
                data.get("event_timeseries", []),
            ),
            **data,
        }


class SessionsView(AnalyticsBase):
    """Session list with device, geo, duration, and pages viewed."""

    template_name = "analytics/sessions.html"
    _charts = [
        ChartMapping("sessions_chart_data", build_session_duration_chart_data, "sessions"),
    ]

    def _call_service(self) -> dict:
        page = safe_int(self.request.GET.get("page"))
        return get_sessions_data(self.website_id, self.date_range, self.filters, page=page)


class DevicesView(AnalyticsBase):
    """Device dimension charts: browser, OS, device type, screen, language."""

    template_name = "analytics/devices.html"
    _charts = [
        ChartMapping("browser_chart_data", build_dimension_chart_data, "browser"),
        ChartMapping("os_chart_data", build_dimension_chart_data, "os"),
        ChartMapping("device_chart_data", build_dimension_chart_data, "device"),
        ChartMapping("language_chart_data", build_dimension_chart_data, "language"),
        ChartMapping("screen_chart_data", build_dimension_chart_data, "screen"),
    ]

    def _call_service(self) -> dict:
        return get_devices_data(self.website_id, self.date_range, self.filters)


class GeoView(AnalyticsBase):
    """Geographic visitor distribution with country/region/city drill-down."""

    template_name = "analytics/geo.html"

    def get_service_data(self) -> dict:
        data = get_geo_data(
            self.website_id,
            self.date_range,
            self.filters,
            country=self.request.GET.get("country") or None,
            region=self.request.GET.get("region") or None,
        )
        data["geo_bubble_data"] = build_geo_bubble_data(data.get("geo", []))
        if data.get("level") == "country":
            data["country_pie_data"] = build_generic_pie_data(
                data.get("country_breakdown", []), "country", "visitors",
            )
            data["regions_bar_data"] = build_geo_regions_bar_data(
                data.get("top_regions", []),
            )
            data["duration_bar_data"] = build_geo_duration_bar_data(
                data.get("geo", []),
            )
        return data


# ============================================================================
# Advanced pages — some need custom context assembly
# ============================================================================


class CompareView(AnalyticsBase):
    """Current vs previous period comparison with stat cards and overlay chart."""

    template_name = "analytics/compare.html"

    def get_service_data(self) -> dict:
        mode = self.request.GET.get("mode", "previous_period")
        data = get_compare_data(
            self.website_id,
            self.date_range,
            self.filters,
            comparison_mode=mode,
        )
        return {
            # build_comparison_chart_data takes two separate lists (current + previous),
            # so it doesn't fit the standard single-key ChartMapping
            "compare_chart_data": build_comparison_chart_data(
                data.get("current_ts", []),
                data.get("previous_ts", []),
            ),
            **data,
        }


class RetentionView(AnalyticsBase):
    """Cohort retention analysis with week or month granularity."""

    template_name = "analytics/retention.html"
    _charts = [ChartMapping("retention_chart_data", build_retention_curve_data, "cohorts")]

    def _call_service(self) -> dict:
        granularity = self.request.GET.get("granularity", "week")
        return get_retention_data(
            self.website_id,
            self.date_range,
            granularity=granularity,
        )


class FunnelsView(AnalyticsBase):
    """Multi-step funnel conversion analysis with configurable steps."""

    template_name = "analytics/funnels.html"
    _charts = [ChartMapping("funnel_chart_data", build_funnel_chart_data, "funnel_steps")]

    def _call_service(self) -> dict:
        steps = parse_funnel_steps(self.request.GET) or None
        window_minutes = safe_int(self.request.GET.get("window", "60"), default=60)
        return get_funnels_data(
            self.website_id,
            self.date_range,
            steps=steps,
            window_minutes=window_minutes,
        )


class JourneysView(AnalyticsBase):
    """User journey paths with Sankey diagram and entry/exit analysis.

    Calls two service functions (journeys + entry/exit) and builds two
    chart payloads with non-standard signatures, so it needs a full
    ``get_service_data`` override.
    """

    template_name = "analytics/journeys.html"

    def get_service_data(self) -> dict:
        path_length = safe_int(self.request.GET.get("path_length", "3"), default=3)
        # Clamp path length to a sane range: 2–10 steps
        path_length = max(2, min(path_length, 10))
        mode = self.request.GET.get("mode", "sections")

        data = get_journeys_data(
            self.website_id,
            self.date_range,
            path_length=path_length,
            mode=mode,
        )
        data["path_length"] = path_length

        entry_exit = get_entry_exit_data(self.website_id, self.date_range, self.filters)
        return {
            "conversion_chart_data": build_conversion_chart_data(
                data.get("conversions", []),
            ),
            "entry_exit_chart_data": build_entry_exit_chart_data(
                entry_exit.get("entry_pages", []),
                entry_exit.get("exit_pages", []),
            ),
            **data,
            **entry_exit,
        }


class RevenueView(AnalyticsBase):
    """Revenue overview: summary, time series, breakdown by event and country."""

    template_name = "analytics/revenue.html"
    _charts = [ChartMapping("country_chart_data", build_revenue_country_chart_data, "by_country")]

    def _call_service(self) -> dict:
        return get_revenue_data(self.website_id, self.date_range)


class EngagementView(AnalyticsBase):
    """Engagement metrics: duration distribution, bounce rates, and traffic heatmap.

    Merges two independent service results (engagement + heatmap),
    so it needs a full ``get_service_data`` override.
    """

    template_name = "analytics/engagement.html"

    def get_service_data(self) -> dict:
        data = get_engagement_data(self.website_id, self.date_range, self.filters)
        heatmap = get_heatmap_data(self.website_id, self.date_range, self.filters)
        return {
            "duration_chart_data": build_duration_by_page_chart_data(
                data.get("duration_by_page", []),
            ),
            "bounce_source_chart_data": build_bounce_by_source_chart_data(
                data.get("bounce_by_source", []),
            ),
            **data,
            **heatmap,
        }


class EntryExitView(AnalyticsBase):
    """Entry and exit page rankings with percentage breakdowns."""

    template_name = "analytics/entry_exit.html"

    def _call_service(self) -> dict:
        return get_entry_exit_data(self.website_id, self.date_range, self.filters)


class HeatmapView(AnalyticsBase):
    """7x24 traffic heatmap grid by day-of-week and hour."""

    template_name = "analytics/heatmap.html"

    def _call_service(self) -> dict:
        return get_heatmap_data(self.website_id, self.date_range, self.filters)


# ============================================================================
# Realtime — no date-range constraint, just the live feed
# ============================================================================


class RealtimeView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    BaseContextMixin,
    TemplateView,
):
    """Live visitor dashboard — active visitors, recent events, current pages.

    Unlike other analytics pages, the realtime view does not depend on a
    date range (live data is always "now").  It inherits the full mixin
    stack for the website selector and filter bar, but skips the
    ``AnalyticsBase`` date-range gate.
    """

    template_name = "analytics/realtime.html"

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        if not self.website_id:
            ctx["no_data"] = True
            return ctx
        return {**ctx, **get_realtime_data(self.website_id)}
