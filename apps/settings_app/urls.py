"""URL routes for the settings app (API keys, bot config, sites)."""

from __future__ import annotations

from django.urls import path

from apps.settings_app.views import (
    ApiKeyCreateView,
    ApiKeyDeleteView,
    ApiKeyListView,
    BotConfigView,
    SettingsIndexView,
    SiteCreateView,
    SiteDeleteView,
    SiteListView,
)

urlpatterns = [
    path("settings/", SettingsIndexView.as_view(), name="settings_index"),
    path("settings/sites/", SiteListView.as_view(), name="site_list"),
    path("settings/sites/create/", SiteCreateView.as_view(), name="site_create"),
    path(
        "settings/sites/<uuid:site_id>/delete/",
        SiteDeleteView.as_view(),
        name="site_delete",
    ),
    path("settings/api-keys/", ApiKeyListView.as_view(), name="api_key_list"),
    path("settings/api-keys/create/", ApiKeyCreateView.as_view(), name="api_key_create"),
    path(
        "settings/api-keys/<uuid:key_id>/delete/",
        ApiKeyDeleteView.as_view(),
        name="api_key_delete",
    ),
    path("settings/bot-config/", BotConfigView.as_view(), name="bot_config"),
]
