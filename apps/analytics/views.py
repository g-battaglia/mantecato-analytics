"""Analytics page views — full-page endpoints for privacy-first aggregate analytics.

Supported pages:
- Overview: total pageviews, trends, top pages, device breakdowns, geo, heatmap
- Pages: per-URL pageview counts
- Sections: URL-prefix pageview groupings
- Devices: browser, OS, device breakdowns
- Geo: country/region/city pageview distribution
- Sources: top referrer domains (referrer **domain** only — no full URL/UTM)
- Compare: current vs previous period pageview comparison
- Heatmap: 7x24 traffic heatmap
- Realtime: live pageview feed

Removed pages (require persistent identifiers):
- Sessions, Retention, Funnels, Journeys, Revenue, Entry/Exit
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.analytics.chart_data import (
    build_dimension_chart_data,
    build_events_bar_chart_data,
    build_events_timeline_data,
    build_generic_pie_data,
    build_geo_bubble_data,
    build_pages_bar_chart_data,
    build_sections_bar_chart_data,
    build_timeseries_chart_data,
)
from apps.analytics.services import (
    get_compare_data,
    get_devices_data,
    get_events_data,
    get_geo_data,
    get_heatmap_data,
    get_landing_data,
    get_overview_data,
    get_pages_data,
    get_sections_data,
    get_sources_data,
    resolve_websites_for_user,  # noqa: F401 — test patch target
)
from apps.analytics.view_utils import AnalyticsBase, ChartMapping
from apps.common.http import safe_int
from apps.common.mixins import (
    BaseContextMixin,
    DateRangeMixin,
    FiltersMixin,
    WebsiteContextMixin,
)


class OverviewView(AnalyticsBase):
    """Default analytics landing page with pageview stats, charts, and HTMX tabs."""

    template_name = "analytics/overview.html"

    def get_service_data(self) -> dict:
        data = get_overview_data(
            self.website_id, self.date_range, self.filters, granularity=self.granularity
        )
        return {
            "stats": data["stats"],
            "timeseries_data": build_timeseries_chart_data(
                data.get("timeseries", []),
                data.get("prev_timeseries", []),
            ),
            "prev_timeseries": data.get("prev_timeseries", []),
            "sections": data["sections"],
            "top_pages": data["top_pages"],
            "event_metrics": data.get("event_metrics", []),
            "browser": data.get("browser", []),
            "os_data": data.get("os_data", data.get("os", [])),
            "device_data": data.get("device_data", data.get("device", [])),
            "country": data["country"],
            "geo": data["geo"],
            "realtime": data["realtime"],
            "recent_events": data["recent_events"],
            "current_pages": data["current_pages"],
            "heatmap": data["heatmap"],
            "active_tab": self.request.GET.get("tab", "pages"),
            # Referrers/Channels panel (referrer-domain only — no UTM).
            "top_referrers": data.get("top_referrers", []),
            "channels": data.get("channels", []),
        }


class PagesView(AnalyticsBase):
    """Per-URL pageview analytics."""

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


class DevicesView(AnalyticsBase):
    """Device dimension charts: browser, OS, device type."""

    template_name = "analytics/devices.html"

    def get_service_data(self) -> dict:
        data = get_devices_data(self.website_id, self.date_range, self.filters)
        return {
            **data,
            "browser_chart_data": build_dimension_chart_data(data["browser"]),
            "os_chart_data": build_dimension_chart_data(data["os"]),
            "device_chart_data": build_dimension_chart_data(data["device"]),
        }


class GeoView(AnalyticsBase):
    """Geographic pageview distribution (country-level only).

    Country-level pageview data drives a Leaflet bubble world map and a
    Top-Countries chart. Region/city drill-down and bounce/duration metrics
    are intentionally absent (no region/city columns, no session storage).
    """

    template_name = "analytics/geo.html"

    def get_service_data(self) -> dict:
        data = get_geo_data(self.website_id, self.date_range, self.filters)
        geo = data.get("geo", [])
        data["geo_bubble_data"] = build_geo_bubble_data(geo)
        data["country_pie_data"] = build_generic_pie_data(geo, "country", "pageviews")
        return data


class SourcesView(AnalyticsBase):
    """Traffic sources — top referrer domains (referrer domain only)."""

    template_name = "analytics/sources.html"

    def get_service_data(self) -> dict:
        data = get_sources_data(self.website_id, self.date_range, self.filters)
        data["sources_chart_data"] = build_generic_pie_data(
            data.get("sources", []), "referrer", "pageviews"
        )
        return data


class EntryPagesView(AnalyticsBase):
    """Entry (landing) pages with visits and engaged bounce rate."""

    template_name = "analytics/entry_pages.html"

    def get_service_data(self) -> dict:
        data = get_landing_data(self.website_id, self.date_range, self.filters)
        data["entry_chart_data"] = build_generic_pie_data(
            data.get("landing", []), "entry_path", "visits"
        )
        return data


class CompareView(AnalyticsBase):
    """Current vs previous period pageview comparison."""

    template_name = "analytics/compare.html"

    def get_service_data(self) -> dict:
        mode = self.request.GET.get("mode", "previous_period")
        data = get_compare_data(
            self.website_id,
            self.date_range,
            self.filters,
            comparison_mode=mode,
            granularity=self.granularity,
        )
        return {
            **data,
            "compare_chart_data": build_timeseries_chart_data(
                data["current_ts"],
                data["previous_ts"],
            ),
        }


class HeatmapView(AnalyticsBase):
    """7x24 traffic heatmap grid by day-of-week and hour."""

    template_name = "analytics/heatmap.html"

    def _call_service(self) -> dict:
        return get_heatmap_data(self.website_id, self.date_range, self.filters)


class RealtimeView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    BaseContextMixin,
    TemplateView,
):
    """Live pageview dashboard — recent pageviews, current pages."""

    template_name = "analytics/realtime.html"

    def get_context_data(self, **kwargs: object) -> dict:
        ctx = super().get_context_data(**kwargs)
        if not self.website_id:
            ctx["no_data"] = True
            return ctx

        from django.utils import timezone

        from apps.analytics.services import get_overview_data
        from core.mantecato_core.date_utils import DateRange

        now = timezone.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        dr = DateRange(start_date=start, end_date=now)
        data = get_overview_data(self.website_id, dr, self.filters, granularity="hour")
        return {**ctx, **data}


class EventsView(AnalyticsBase):
    """Aggregate custom-event analytics by event name."""

    template_name = "analytics/events.html"

    def get_service_data(self) -> dict:
        data = get_events_data(
            self.website_id,
            self.date_range,
            self.filters,
            granularity=self.granularity,
        )
        return {
            **data,
            # Bar and pie share one payload — the chart card toggles between them.
            "events_chart_data": build_events_bar_chart_data(data["events"]),
            "events_timeline_data": build_events_timeline_data(data["event_timeseries"]),
        }
