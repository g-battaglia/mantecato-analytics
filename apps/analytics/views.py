"""Analytics page views — full-page endpoints for privacy-first aggregate analytics.

Supported pages:
- Overview: total pageviews, trends, top pages, device breakdowns, geo, heatmap
- Pages: per-URL pageview counts
- Sections: URL-prefix pageview groupings
- Devices: browser, OS, device breakdowns
- Geo: country/region/city pageview distribution
- Compare: current vs previous period pageview comparison
- Heatmap: 7x24 traffic heatmap
- Realtime: live pageview feed

Removed pages (require persistent identifiers):
- Sessions, Events, Sources, Retention, Funnels, Journeys, Revenue, Engagement, Entry/Exit
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.analytics.services import (
    get_compare_data,
    get_devices_data,
    get_geo_data,
    get_heatmap_data,
    get_overview_data,
    get_pages_data,
    get_sections_data,
    resolve_websites_for_user,  # noqa: F401 — test patch target
)
from apps.analytics.view_utils import AnalyticsBase
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
        data = get_overview_data(self.website_id, self.date_range, self.filters, granularity=self.granularity)
        return {
            "stats": data["stats"],
            "timeseries_data": data.get("timeseries", []),
            "prev_timeseries": data.get("prev_timeseries", []),
            "sections": data["sections"],
            "top_pages": data["top_pages"],
            "browser": data["browser"],
            "os_data": data["os_data"],
            "device_data": data["device_data"],
            "country": data["country"],
            "geo": data["geo"],
            "realtime": data["realtime"],
            "recent_events": data["recent_events"],
            "current_pages": data["current_pages"],
            "heatmap": data["heatmap"],
            "active_tab": self.request.GET.get("tab", "pages"),
        }


class PagesView(AnalyticsBase):
    """Per-URL pageview analytics."""

    template_name = "analytics/pages.html"

    def _call_service(self) -> dict:
        page = safe_int(self.request.GET.get("page"))
        return get_pages_data(self.website_id, self.date_range, self.filters, page=page)


class SectionsView(AnalyticsBase):
    """Site sections breakdown by URL prefix."""

    template_name = "analytics/sections.html"

    def _call_service(self) -> dict:
        return get_sections_data(self.website_id, self.date_range, self.filters)


class DevicesView(AnalyticsBase):
    """Device dimension charts: browser, OS, device type."""

    template_name = "analytics/devices.html"

    def _call_service(self) -> dict:
        return get_devices_data(self.website_id, self.date_range, self.filters)


class GeoView(AnalyticsBase):
    """Geographic pageview distribution (country-level only)."""

    template_name = "analytics/geo.html"

    def get_service_data(self) -> dict:
        return get_geo_data(self.website_id, self.date_range, self.filters)


class CompareView(AnalyticsBase):
    """Current vs previous period pageview comparison."""

    template_name = "analytics/compare.html"

    def get_service_data(self) -> dict:
        mode = self.request.GET.get("mode", "previous_period")
        return get_compare_data(
            self.website_id,
            self.date_range,
            self.filters,
            comparison_mode=mode,
            granularity=self.granularity,
        )


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

        from apps.analytics.services import get_overview_data
        from core.mantecato_core.date_utils import DateRange
        from django.utils import timezone
        now = timezone.now()
        dr = DateRange(start_date=now.replace(hour=0, minute=0, second=0, microsecond=0), end_date=now)
        data = get_overview_data(self.website_id, dr, granularity="hour")
        return {**ctx, **data}
