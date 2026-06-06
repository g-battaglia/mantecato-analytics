"""URL routes for the tracker ingestion endpoints."""

from __future__ import annotations

from django.urls import path

from apps.tracker.views import IngestView, api_script

urlpatterns = [
    path("api/send", IngestView.as_view(), name="tracker_send"),
    path("api/script", api_script, name="tracker_script"),
]
