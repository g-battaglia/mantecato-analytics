"""URL routes for the dashboards app."""

from __future__ import annotations

from django.urls import path

from apps.dashboards.views import (
    DashboardCreateView,
    DashboardDeleteView,
    DashboardListView,
    DashboardUpdateView,
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
]
