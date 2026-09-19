"""Routes for the additive API v1 contract."""

from django.urls import path

from apps.api.v1.views import (
    AnalyticsCompareView,
    AnalyticsQueryView,
    CapabilitiesView,
    DimensionValuesView,
    SchemaView,
    TrafficQualityView,
)

urlpatterns = [
    path("capabilities/", CapabilitiesView.as_view(), name="api_v1_capabilities"),
    path("schema/", SchemaView.as_view(), name="api_v1_schema"),
    path("analytics/query/", AnalyticsQueryView.as_view(), name="api_v1_analytics_query"),
    path("analytics/compare/", AnalyticsCompareView.as_view(), name="api_v1_analytics_compare"),
    path(
        "analytics/traffic-quality/",
        TrafficQualityView.as_view(),
        name="api_v1_traffic_quality",
    ),
    path(
        "analytics/dimension-values/",
        DimensionValuesView.as_view(),
        name="api_v1_dimension_values",
    ),
]
