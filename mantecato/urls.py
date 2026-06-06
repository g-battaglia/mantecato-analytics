from django.urls import include, path

urlpatterns = [
    path("", include("apps.tracker.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.dashboards.urls")),
    path("", include("apps.settings_app.urls")),
    path("", include("apps.core.urls")),
    path("api/", include("apps.api.urls")),
]
