"""URL routes for the dashboards app."""

from __future__ import annotations

from django.urls import path

from apps.dashboards.views import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardDetailView,
    DashboardListView,
    DashboardUpdateView,
    DashboardWidgetPreviewView,
    DashboardWidgetView,
)

urlpatterns = [
    path("dashboards/", DashboardListView.as_view(), name="dashboard_list"),
    path("dashboards/create/", DashboardCreateView.as_view(), name="dashboard_create"),
    path(
        "dashboards/<uuid:report_id>/edit/",
        DashboardUpdateView.as_view(),
        name="dashboard_edit",
    ),
    path(
        "dashboards/<uuid:report_id>/delete/",
        DashboardDeleteView.as_view(),
        name="dashboard_delete",
    ),
    # Rendered dashboard + its per-widget HTMX partial (literal routes above win).
    path(
        "dashboards/<uuid:report_id>/preview-widget/",
        DashboardWidgetPreviewView.as_view(),
        name="dashboard_widget_preview",
    ),
    path(
        "dashboards/<uuid:report_id>/widget/<str:widget_id>/",
        DashboardWidgetView.as_view(),
        name="dashboard_widget",
    ),
    path(
        "dashboards/<uuid:report_id>/",
        DashboardDetailView.as_view(),
        name="dashboard_detail",
    ),
]
