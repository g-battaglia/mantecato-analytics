"""URL routes for the analytics web pages and HTMX partials.

Only aggregate pageview analytics are supported.
Removed: sessions, events, sources, retention, funnels, journeys, revenue,
engagement, entry/exit routes.
"""

from __future__ import annotations

from django.urls import path

# HTMX partial views
from apps.analytics.partials import (
    FilterValuesView,
    OverviewTabView,
    RealtimePartialView,
)

# Full-page views
from apps.analytics.views import (
    CompareView,
    DevicesView,
    GeoView,
    HeatmapView,
    OverviewView,
    PagesView,
    RealtimeView,
    SectionsView,
)

urlpatterns = [
    path("", OverviewView.as_view(), name="overview"),
    path("overview/tab/", OverviewTabView.as_view(), name="overview_tab"),
    path("filter-values/", FilterValuesView.as_view(), name="analytics_filter_values"),
    path("pages/", PagesView.as_view(), name="analytics_pages"),
    path("sections/", SectionsView.as_view(), name="analytics_sections"),
    path("devices/", DevicesView.as_view(), name="analytics_devices"),
    path("geo/", GeoView.as_view(), name="analytics_geo"),
    path("compare/", CompareView.as_view(), name="analytics_compare"),
    path("heatmap/", HeatmapView.as_view(), name="analytics_heatmap"),
    path("realtime/", RealtimeView.as_view(), name="analytics_realtime"),
    path("realtime/partial/", RealtimePartialView.as_view(), name="analytics_realtime_partial"),
]
