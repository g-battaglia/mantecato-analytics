"""URL routes for the JSON API."""

from __future__ import annotations

from django.urls import path

from apps.api.views import (
    AnalyticsCompareView,
    AnalyticsDevicesView,
    AnalyticsEngagementView,
    AnalyticsEventsView,
    AnalyticsFunnelsView,
    AnalyticsGeoView,
    AnalyticsJourneysView,
    AnalyticsOverviewView,
    AnalyticsPagesView,
    AnalyticsRealtimeView,
    AnalyticsRetentionView,
    AnalyticsRevenueView,
    AnalyticsSessionsView,
    AnalyticsSourcesView,
    ApiKeyCreateView,
    ApiKeyDeleteView,
    ApiKeyListView,
    BotConfigGetView,
    BotConfigSaveView,
    DashboardCreateView,
    DashboardDeleteView,
    DashboardDetailView,
    DashboardListView,
    DashboardUpdateView,
    SitesListView,
)

urlpatterns = [
    # Sites (legacy MCP path without trailing slash kept for compat)
    path("sites", SitesListView.as_view(), name="api_sites_list_legacy"),
    path("sites/", SitesListView.as_view(), name="api_sites_list"),
    # Analytics
    path("analytics/overview/", AnalyticsOverviewView.as_view(), name="api_analytics_overview"),
    path("analytics/pages/", AnalyticsPagesView.as_view(), name="api_analytics_pages"),
    path("analytics/sources/", AnalyticsSourcesView.as_view(), name="api_analytics_sources"),
    path("analytics/events/", AnalyticsEventsView.as_view(), name="api_analytics_events"),
    path("analytics/sessions/", AnalyticsSessionsView.as_view(), name="api_analytics_sessions"),
    path("analytics/devices/", AnalyticsDevicesView.as_view(), name="api_analytics_devices"),
    path("analytics/geo/", AnalyticsGeoView.as_view(), name="api_analytics_geo"),
    path("analytics/compare/", AnalyticsCompareView.as_view(), name="api_analytics_compare"),
    path("analytics/retention/", AnalyticsRetentionView.as_view(), name="api_analytics_retention"),
    path("analytics/funnels/", AnalyticsFunnelsView.as_view(), name="api_analytics_funnels"),
    path("analytics/journeys/", AnalyticsJourneysView.as_view(), name="api_analytics_journeys"),
    path("analytics/revenue/", AnalyticsRevenueView.as_view(), name="api_analytics_revenue"),
    path(
        "analytics/engagement/", AnalyticsEngagementView.as_view(), name="api_analytics_engagement"
    ),
    path("analytics/realtime/", AnalyticsRealtimeView.as_view(), name="api_analytics_realtime"),
    # Dashboards
    path("dashboards/", DashboardListView.as_view(), name="api_dashboard_list"),
    path(
        "dashboards/<uuid:report_id>/", DashboardDetailView.as_view(), name="api_dashboard_detail"
    ),
    path("dashboards/create/", DashboardCreateView.as_view(), name="api_dashboard_create"),
    path(
        "dashboards/<uuid:report_id>/update/",
        DashboardUpdateView.as_view(),
        name="api_dashboard_update",
    ),
    path(
        "dashboards/<uuid:report_id>/delete/",
        DashboardDeleteView.as_view(),
        name="api_dashboard_delete",
    ),
    # API Keys
    path("api-keys/", ApiKeyListView.as_view(), name="api_api_key_list"),
    path("api-keys/create/", ApiKeyCreateView.as_view(), name="api_api_key_create"),
    path("api-keys/<uuid:key_id>/delete/", ApiKeyDeleteView.as_view(), name="api_api_key_delete"),
    # Bot Config
    path("bot-config/", BotConfigGetView.as_view(), name="api_bot_config_get"),
    path("bot-config/save/", BotConfigSaveView.as_view(), name="api_bot_config_save"),
]
