"""HTMX partial views — lightweight fragments returned inside the analytics pages.

Only aggregate pageview-related partials are supported.
Removed: session activity, event properties, engagement bucket, time-on-page,
journey section detail, next pages (all require session tracking).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from apps.analytics.services import (
    get_overview_tab_devices,
    get_overview_tab_events,
    get_overview_tab_geo,
    get_overview_tab_pages,
    resolve_websites_for_user,  # noqa: F401  — imported so tests can patch it here
)
from apps.common.mixins import (
    DateRangeMixin,
    FiltersMixin,
    GranularityMixin,
    WebsiteContextMixin,
)
from core.mantecato_core.queries.filter_values import get_filter_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest


# ============================================================================
# Overview tab registry
# ============================================================================


class _TabConfig(NamedTuple):
    """Pair of (template_path, data_fetcher) for one overview tab."""
    template: str
    fetcher: Callable


_OVERVIEW_TABS: dict[str, _TabConfig] = {
    "pages": _TabConfig("analytics/_tab_pages.html", get_overview_tab_pages),
    "events": _TabConfig("analytics/_tab_events.html", get_overview_tab_events),
    "devices": _TabConfig("analytics/_tab_devices.html", get_overview_tab_devices),
    "geo": _TabConfig("analytics/_tab_geo.html", get_overview_tab_geo),
}


# ============================================================================
# Base class
# ============================================================================


class _HtmxPartialBase(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    GranularityMixin,
    FiltersMixin,
    View,
):
    """Abstract base for HTMX partial views."""

    template_name: str
    required_param: str | None = None
    require_date_range: bool = True

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not self.website_id:
            return HttpResponse("")
        if self.require_date_range and not self.date_range:
            return HttpResponse("")
        param_value: str | None = None
        if self.required_param:
            param_value = request.GET.get(self.required_param, "")
            if not param_value:
                return HttpResponse("")
        ctx = self.get_partial_data(request, param_value)
        return render(request, self.template_name, ctx)

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        return {}


# ============================================================================
# Concrete partials
# ============================================================================


class OverviewTabView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    View,
):
    """HTMX partial — renders a single tab body fragment of the overview page."""

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not self.website_id or not self.date_range:
            return HttpResponse("")
        tab = request.GET.get("tab", "pages")
        config = _OVERVIEW_TABS.get(tab, _OVERVIEW_TABS["pages"])
        data = config.fetcher(self.website_id, self.date_range, self.filters)
        return render(request, config.template, {"active_tab": tab, **data})


class RealtimePartialView(
    LoginRequiredMixin,
    WebsiteContextMixin,
    DateRangeMixin,
    FiltersMixin,
    View,
):
    """HTMX partial — realtime data refreshed by a polling loop."""

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not self.website_id:
            return HttpResponse("")
        from apps.analytics.services import get_overview_data
        from core.mantecato_core.date_utils import DateRange
        from django.utils import timezone
        now = timezone.now()
        dr = DateRange(start_date=now.replace(hour=0, minute=0, second=0, microsecond=0), end_date=now)
        data = get_overview_data(self.website_id, dr, self.filters, granularity="hour")
        return render(
            request,
            "analytics/_realtime_data.html",
            {"selected_website": self.website_id, **data},
        )


class FilterValuesView(_HtmxPartialBase):
    """HTMX partial — distinct values for a column, powering the filter typeahead."""

    template_name = "analytics/_filter_values.html"
    required_param = "column"

    def get_partial_data(self, request: HttpRequest, param_value: str | None) -> dict:
        search = request.GET.get("search", "").strip() or None
        values = get_filter_values(
            self.website_id,
            param_value,
            self.date_range.start_date,
            self.date_range.end_date,
            search=search,
            limit=20,
        )
        return {"values": values}

