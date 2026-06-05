"""URL routes for the analytics web pages and HTMX partials.

Full-page views live in ``apps.analytics.views``; HTMX partial endpoints
(tab fragments, drill-downs, polling responses) live in
``apps.analytics.partials``.  Both are wired into a single flat URL list
so the browser/HTMX sees one coherent namespace.
"""

from __future__ import annotations

from django.urls import path

# HTMX partial views — return HTML fragments for in-page swap
from apps.analytics.partials import (
    EngagementBucketDetailView,
    EventPropertiesView,
    FilterValuesView,
    JourneySectionDetailView,
    NextPagesView,
    OverviewTabView,
    RealtimePartialView,
    SessionActivityView,
    TimeOnPageDetailView,
)

# Full-page views — each renders a complete HTML document
from apps.analytics.views import (
    CompareView,
    DevicesView,
    EngagementView,
    EventsView,
    FunnelsView,
    GeoView,
    JourneysView,
    OverviewView,
    PagesView,
    RealtimeView,
    RetentionView,
    RevenueView,
    SectionsView,
    SessionsView,
    SourcesView,
)

urlpatterns = [
    path("", OverviewView.as_view(), name="overview"),
    path("overview/tab/", OverviewTabView.as_view(), name="overview_tab"),
    path("filter-values/", FilterValuesView.as_view(), name="analytics_filter_values"),
    path("pages/", PagesView.as_view(), name="analytics_pages"),
    path("pages/next/", NextPagesView.as_view(), name="analytics_next_pages"),
    path("sections/", SectionsView.as_view(), name="analytics_sections"),
    path("sources/", SourcesView.as_view(), name="analytics_sources"),
    path("events/", EventsView.as_view(), name="analytics_events"),
    path("events/properties/", EventPropertiesView.as_view(), name="analytics_event_properties"),
    path("sessions/", SessionsView.as_view(), name="analytics_sessions"),
    path("sessions/activity/", SessionActivityView.as_view(), name="analytics_session_activity"),
    path("devices/", DevicesView.as_view(), name="analytics_devices"),
    path("geo/", GeoView.as_view(), name="analytics_geo"),
    path("compare/", CompareView.as_view(), name="analytics_compare"),
    path("retention/", RetentionView.as_view(), name="analytics_retention"),
    path("funnels/", FunnelsView.as_view(), name="analytics_funnels"),
    path("journeys/", JourneysView.as_view(), name="analytics_journeys"),
    path(
        "journeys/section-detail/",
        JourneySectionDetailView.as_view(),
        name="analytics_journey_section_detail",
    ),
    path("revenue/", RevenueView.as_view(), name="analytics_revenue"),
    path("engagement/", EngagementView.as_view(), name="analytics_engagement"),
    path(
        "engagement/bucket/",
        EngagementBucketDetailView.as_view(),
        name="analytics_engagement_bucket",
    ),
    path("engagement/time-on-page/", TimeOnPageDetailView.as_view(), name="analytics_time_on_page"),
    path("realtime/", RealtimeView.as_view(), name="analytics_realtime"),
    path("realtime/partial/", RealtimePartialView.as_view(), name="analytics_realtime_partial"),
]
