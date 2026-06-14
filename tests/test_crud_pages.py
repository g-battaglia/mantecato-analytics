"""Tests for Phase 5 CRUD pages — dashboards, settings, API keys, bot config.

Covers:
- URL resolution and login requirement for all CRUD routes
- GET renders list/form views with mocked services
- POST create/update/delete calls expected service functions and redirects
- No GET mutation (delete via GET redirects)
- Templates exist, extend base, use i18n, contain forms/CSRF markers
- Base nav Dashboards/Settings use real {% url %} tags
- No forbidden JS frameworks in new templates
- Static safety: no SQL writes on read-only tables from view/service code
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.http import HttpResponse
    from django.test import Client

from apps.core.models import MantecatoUser

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
WEBSITE_ID = "a0000000-0000-0000-0000-000000000001"
REPORT_ID = "c0000000-0000-0000-0000-000000000001"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
DASHBOARDS_DIR = TEMPLATES_DIR / "dashboards"
SETTINGS_DIR = TEMPLATES_DIR / "settings"
BASE_HTML = TEMPLATES_DIR / "base.html"


def _login_as_admin(client: Client) -> None:
    """Authenticate via ``client.force_login`` (no DB hit, no /login/ POST).

    Patches the ``user_logged_in`` signal's ``send`` so Django's stock
    ``update_last_login`` receiver never runs (it would otherwise ``UPDATE``
    the user row and require a real database).
    """
    from django.contrib.auth.signals import user_logged_in

    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)


@contextmanager
def _patch_middleware_user() -> Generator[None, None, None]:
    """Patch middleware's user lookup for the duration of the context."""
    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    with patch(
        "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"
    ) as mock_process:

        def _set_user(request):
            request.user = user

        mock_process.side_effect = _set_user
        yield


def _authed_get(client: Client, url: str) -> HttpResponse:
    """Login as admin, patch middleware, and GET a URL."""
    _login_as_admin(client)
    with _patch_middleware_user():
        return client.get(url)


def _authed_post(client: Client, url: str, data: dict | None = None) -> HttpResponse:
    """Login as admin, patch middleware, and POST to a URL."""
    _login_as_admin(client)
    with _patch_middleware_user():
        return client.post(url, data or {})


# ---------------------------------------------------------------------------
# URL Resolution
# ---------------------------------------------------------------------------


class TestURLResolution:
    def test_dashboard_list_url(self) -> None:
        from django.urls import reverse

        assert reverse("dashboard_list") == "/dashboards/"

    def test_dashboard_create_url(self) -> None:
        from django.urls import reverse

        assert reverse("dashboard_create") == "/dashboards/create/"

    def test_dashboard_edit_url(self) -> None:
        from django.urls import reverse

        url = reverse("dashboard_edit", kwargs={"report_id": REPORT_ID})
        assert url == f"/dashboards/{REPORT_ID}/edit/"

    def test_dashboard_delete_url(self) -> None:
        from django.urls import reverse

        url = reverse("dashboard_delete", kwargs={"report_id": REPORT_ID})
        assert url == f"/dashboards/{REPORT_ID}/delete/"

    def test_settings_index_url(self) -> None:
        from django.urls import reverse

        assert reverse("settings_index") == "/settings/"

    def test_api_key_list_url(self) -> None:
        from django.urls import reverse

        assert reverse("api_key_list") == "/settings/api-keys/"

    def test_api_key_create_url(self) -> None:
        from django.urls import reverse

        assert reverse("api_key_create") == "/settings/api-keys/create/"

    def test_api_key_delete_url(self) -> None:
        from django.urls import reverse

        url = reverse("api_key_delete", kwargs={"key_id": REPORT_ID})
        assert url == f"/settings/api-keys/{REPORT_ID}/delete/"

    def test_bot_config_url(self) -> None:
        from django.urls import reverse

        assert reverse("bot_config") == "/settings/bot-config/"

    def test_site_purge_url(self) -> None:
        from django.urls import reverse

        url = reverse("site_purge", kwargs={"site_id": WEBSITE_ID})
        assert url == f"/settings/sites/{WEBSITE_ID}/purge/"


# ---------------------------------------------------------------------------
# Login Requirement
# ---------------------------------------------------------------------------


class TestLoginRequired:
    ROUTES_GET = [
        "/dashboards/",
        "/dashboards/create/",
        f"/dashboards/{REPORT_ID}/edit/",
        "/settings/",
        "/settings/api-keys/",
        "/settings/bot-config/",
    ]

    ROUTES_POST = [
        "/dashboards/create/",
        f"/dashboards/{REPORT_ID}/delete/",
        "/settings/api-keys/create/",
        f"/settings/sites/{WEBSITE_ID}/purge/",
    ]

    @pytest.mark.parametrize("url", ROUTES_GET)
    def test_get_redirects_to_login(self, client: Client, url: str) -> None:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    @pytest.mark.parametrize("url", ROUTES_POST)
    def test_post_redirects_to_login(self, client: Client, url: str) -> None:
        response = client.post(url, {})
        assert response.status_code == 302
        assert "/login/" in response.url


# ---------------------------------------------------------------------------
# Dashboard Views
# ---------------------------------------------------------------------------


class TestDashboardListView:
    @patch("apps.dashboards.views.get_dashboards_for_user")
    def test_renders_list(self, mock_list: MagicMock, client: Client) -> None:
        mock_list.return_value = [
            {
                "id": REPORT_ID,
                "name": "My Dashboard",
                "description": "Test",
                "updatedAt": "2025-01-01T00:00:00",
            },
        ]
        response = _authed_get(client, "/dashboards/")
        assert response.status_code == 200
        assert "My Dashboard" in response.content.decode()

    @patch("apps.dashboards.views.get_dashboards_for_user")
    def test_service_called_with_user_id(self, mock_list: MagicMock, client: Client) -> None:
        mock_list.return_value = []
        _authed_get(client, "/dashboards/")
        mock_list.assert_called_once_with(ADMIN_USER_ID)


class TestDashboardCreateView:
    def test_get_renders_form(self, client: Client) -> None:
        response = _authed_get(client, "/dashboards/create/")
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="name"' in content
        assert 'name="website_id"' in content
        assert "csrfmiddlewaretoken" in content

    @patch("apps.dashboards.views.create_new_dashboard")
    def test_post_creates_and_redirects(self, mock_create: MagicMock, client: Client) -> None:
        mock_create.return_value = {"id": REPORT_ID}
        response = _authed_post(
            client,
            "/dashboards/create/",
            {
                "name": "New Dash",
                "description": "Desc",
                "website_id": WEBSITE_ID,
                "config": '{"version": 1}',
            },
        )
        assert response.status_code == 302
        mock_create.assert_called_once()

    @patch("apps.dashboards.views.create_new_dashboard")
    def test_post_empty_name_shows_error(self, mock_create: MagicMock, client: Client) -> None:
        response = _authed_post(
            client,
            "/dashboards/create/",
            {"name": "", "website_id": WEBSITE_ID},
        )
        assert response.status_code == 200
        mock_create.assert_not_called()


class TestDashboardEditView:
    @patch("apps.dashboards.views.get_dashboard_detail")
    def test_get_renders_form(self, mock_get: MagicMock, client: Client) -> None:
        mock_get.return_value = {
            "id": REPORT_ID,
            "name": "My Dash",
            "description": "",
            "websiteId": WEBSITE_ID,
            "config": {},
        }
        response = _authed_get(client, f"/dashboards/{REPORT_ID}/edit/")
        assert response.status_code == 200
        assert "My Dash" in response.content.decode()

    @patch("apps.dashboards.views.get_dashboard_detail")
    def test_get_not_found_redirects(self, mock_get: MagicMock, client: Client) -> None:
        mock_get.return_value = None
        response = _authed_get(client, f"/dashboards/{REPORT_ID}/edit/")
        assert response.status_code == 302

    @patch("apps.dashboards.views.update_existing_dashboard")
    @patch("apps.dashboards.views.get_dashboard_detail")
    def test_post_updates_and_redirects(
        self,
        mock_get: MagicMock,
        mock_update: MagicMock,
        client: Client,
    ) -> None:
        mock_get.return_value = {
            "id": REPORT_ID,
            "name": "Dash",
            "description": "",
            "websiteId": WEBSITE_ID,
            "config": {},
        }
        mock_update.return_value = {"id": REPORT_ID}
        response = _authed_post(
            client,
            f"/dashboards/{REPORT_ID}/edit/",
            {"name": "Updated", "description": "New desc", "config": "{}"},
        )
        assert response.status_code == 302
        mock_update.assert_called_once()


class TestDashboardDeleteView:
    @patch("apps.dashboards.views.remove_dashboard")
    def test_post_deletes_and_redirects(self, mock_del: MagicMock, client: Client) -> None:
        mock_del.return_value = True
        response = _authed_post(client, f"/dashboards/{REPORT_ID}/delete/")
        assert response.status_code == 302
        mock_del.assert_called_once()
        args = mock_del.call_args[0]
        assert str(args[0]) == REPORT_ID
        assert args[1] == ADMIN_USER_ID

    @patch("apps.dashboards.views.remove_dashboard")
    def test_get_delete_redirects_no_mutation(self, mock_del: MagicMock, client: Client) -> None:
        response = _authed_get(client, f"/dashboards/{REPORT_ID}/delete/")
        assert response.status_code == 302
        mock_del.assert_not_called()


# ---------------------------------------------------------------------------
# API Key Views
# ---------------------------------------------------------------------------


class TestApiKeyListView:
    @patch("apps.settings_app.views.get_api_keys_for_user")
    def test_renders_list(self, mock_list: MagicMock, client: Client) -> None:
        mock_list.return_value = [
            {
                "id": REPORT_ID,
                "name": "My Key",
                "prefix": "mtk_abc123...",
                "scopes": ["read"],
                "createdAt": "2025-01-01",
            },
        ]
        response = _authed_get(client, "/settings/api-keys/")
        assert response.status_code == 200
        assert "My Key" in response.content.decode()


class TestApiKeyCreateView:
    @patch("apps.settings_app.views.get_api_keys_for_user")
    @patch("apps.settings_app.views.generate_new_api_key")
    def test_post_creates_key(
        self,
        mock_create: MagicMock,
        mock_list: MagicMock,
        client: Client,
    ) -> None:
        mock_create.return_value = {
            "id": REPORT_ID,
            "name": "New",
            "key": "mtk_secretkey123",
            "prefix": "mtk_secretk...",
            "scopes": ["read", "write"],
            "createdAt": "2025-01-01",
        }
        mock_list.return_value = []
        response = _authed_post(
            client,
            "/settings/api-keys/create/",
            {"name": "New", "scopes": "read,write"},
        )
        assert response.status_code == 200
        assert "mtk_secretkey123" in response.content.decode()

    def test_get_redirects_to_list(self, client: Client) -> None:
        response = _authed_get(client, "/settings/api-keys/create/")
        assert response.status_code == 302

    @patch("apps.settings_app.views.get_api_keys_for_user")
    @patch("apps.settings_app.views.generate_new_api_key")
    def test_post_empty_name_shows_error(
        self,
        mock_create: MagicMock,
        mock_list: MagicMock,
        client: Client,
    ) -> None:
        mock_list.return_value = []
        response = _authed_post(client, "/settings/api-keys/create/", {"name": ""})
        assert response.status_code == 302
        mock_create.assert_not_called()

    @patch("apps.settings_app.views.get_api_keys_for_user")
    @patch("apps.settings_app.views.generate_new_api_key")
    def test_post_invalid_scope_shows_error_not_500(
        self,
        mock_create: MagicMock,
        mock_list: MagicMock,
        client: Client,
    ) -> None:
        # A typo'd scope must surface a form error (redirect), never a 500, and
        # the key must not be created.
        mock_list.return_value = []
        response = _authed_post(
            client,
            "/settings/api-keys/create/",
            {"name": "New", "scopes": "read,wrte"},
        )
        assert response.status_code == 302
        mock_create.assert_not_called()


class TestApiKeyDeleteView:
    @patch("apps.settings_app.views.remove_api_key")
    def test_post_deletes(self, mock_del: MagicMock, client: Client) -> None:
        mock_del.return_value = True
        response = _authed_post(client, f"/settings/api-keys/{REPORT_ID}/delete/")
        assert response.status_code == 302

    @patch("apps.settings_app.views.remove_api_key")
    def test_get_delete_no_mutation(self, mock_del: MagicMock, client: Client) -> None:
        response = _authed_get(client, f"/settings/api-keys/{REPORT_ID}/delete/")
        assert response.status_code == 302
        mock_del.assert_not_called()


# ---------------------------------------------------------------------------
# Bot Config Views
# ---------------------------------------------------------------------------


class TestBotConfigView:
    @patch(
        "apps.settings_app.views.resolve_websites_for_user",
        return_value=[{"id": WEBSITE_ID, "name": "Site", "domain": "x"}],
    )
    @patch("apps.settings_app.views.get_bot_config")
    def test_get_with_website_renders_form(
        self, mock_get: MagicMock, mock_sites: MagicMock, client: Client
    ) -> None:
        mock_get.return_value = {"config": {"enabled": False, "knownBots": True}}
        response = _authed_get(client, f"/settings/bot-config/?website={WEBSITE_ID}")
        assert response.status_code == 200
        assert "knownBots" in response.content.decode()

    @patch("apps.settings_app.views.resolve_websites_for_user", return_value=[])
    @patch("apps.settings_app.views.get_bot_config")
    def test_get_foreign_website_is_blocked(
        self, mock_get: MagicMock, mock_sites: MagicMock, client: Client
    ) -> None:
        # IDOR guard: a website the user can't access returns 404, and the
        # config is never read.
        response = _authed_get(client, f"/settings/bot-config/?website={WEBSITE_ID}")
        assert response.status_code == 404
        mock_get.assert_not_called()

    @patch("apps.settings_app.views.resolve_websites_for_user", return_value=[])
    def test_get_without_website_shows_placeholder(
        self, mock_sites: MagicMock, client: Client
    ) -> None:
        response = _authed_get(client, "/settings/bot-config/")
        assert response.status_code == 200

    @patch(
        "apps.settings_app.views.resolve_websites_for_user",
        return_value=[{"id": WEBSITE_ID, "name": "Site", "domain": "x"}],
    )
    @patch("apps.settings_app.views.save_bot_config")
    @patch("apps.settings_app.views.get_bot_config")
    def test_post_saves_config(
        self,
        mock_get: MagicMock,
        mock_save: MagicMock,
        mock_sites: MagicMock,
        client: Client,
    ) -> None:
        mock_save.return_value = {"config": {}}
        mock_get.return_value = {"config": {}}
        # ``excludedCountries`` is now a MultipleChoiceField, so the POST
        # either omits it (no exclusions) or supplies one or more ISO codes.
        response = _authed_post(
            client,
            "/settings/bot-config/",
            {
                "website_id": WEBSITE_ID,
                "enabled": "on",
                "knownBots": "on",
                "clusterBounceThreshold": "90",
                "clusterMinSize": "100",
                "minDuration": "0",
                "highVelocityThreshold": "60",
            },
        )
        assert response.status_code == 302
        mock_save.assert_called_once()

# ---------------------------------------------------------------------------
# Site Purge View
# ---------------------------------------------------------------------------


class TestSitePurgeView:
    @patch("apps.settings_app.views.purge_website_data")
    @patch("apps.settings_app.views.Website")
    def test_post_with_correct_name_purges(
        self, mock_ws: MagicMock, mock_purge: MagicMock, client: Client
    ) -> None:
        site = MagicMock()
        site.name = "My Site"
        mock_ws.objects.filter.return_value.first.return_value = site
        mock_purge.return_value = {"name": "My Site", "events": 500, "visitor_rows": 10}
        response = _authed_post(
            client,
            f"/settings/sites/{WEBSITE_ID}/purge/",
            {"confirm_name": "My Site"},
        )
        assert response.status_code == 302
        mock_purge.assert_called_once()

    @patch("apps.settings_app.views.purge_website_data")
    @patch("apps.settings_app.views.Website")
    def test_post_with_wrong_name_aborts(
        self, mock_ws: MagicMock, mock_purge: MagicMock, client: Client
    ) -> None:
        site = MagicMock()
        site.name = "My Site"
        mock_ws.objects.filter.return_value.first.return_value = site
        response = _authed_post(
            client,
            f"/settings/sites/{WEBSITE_ID}/purge/",
            {"confirm_name": "wrong"},
        )
        assert response.status_code == 302
        mock_purge.assert_not_called()

    @patch("apps.settings_app.views.Website")
    def test_post_missing_site_returns_error(
        self, mock_ws: MagicMock, client: Client
    ) -> None:
        mock_ws.objects.filter.return_value.first.return_value = None
        response = _authed_post(
            client,
            f"/settings/sites/{WEBSITE_ID}/purge/",
            {"confirm_name": "x"},
        )
        assert response.status_code == 302

    def test_get_redirects(self, client: Client) -> None:
        response = _authed_get(client, f"/settings/sites/{WEBSITE_ID}/purge/")
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# Settings Index
# ---------------------------------------------------------------------------


class TestSettingsIndex:
    def test_renders_index(self, client: Client) -> None:
        response = _authed_get(client, "/settings/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "API Keys" in content
        assert "Bot Config" in content


# ---------------------------------------------------------------------------
# Templates: Existence and Structure
# ---------------------------------------------------------------------------


class TestTemplateExistence:
    TEMPLATES = [
        DASHBOARDS_DIR / "dashboard_list.html",
        DASHBOARDS_DIR / "dashboard_form.html",
        SETTINGS_DIR / "index.html",
        SETTINGS_DIR / "api_keys.html",
        SETTINGS_DIR / "bot_config.html",
    ]

    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: str(t.name))
    def test_template_exists(self, template: Path) -> None:
        assert template.is_file(), f"Template must exist: {template}"


class TestTemplatesExtendBase:
    TEMPLATES = [
        DASHBOARDS_DIR / "dashboard_list.html",
        DASHBOARDS_DIR / "dashboard_form.html",
        SETTINGS_DIR / "index.html",
        SETTINGS_DIR / "api_keys.html",
        SETTINGS_DIR / "bot_config.html",
    ]

    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: str(t.name))
    def test_extends_base(self, template: Path) -> None:
        content = template.read_text()
        assert '{% extends "base.html" %}' in content

    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: str(t.name))
    def test_uses_i18n(self, template: Path) -> None:
        content = template.read_text()
        assert "{% load i18n" in content or "{% trans" in content

    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: str(t.name))
    def test_has_trans_tags(self, template: Path) -> None:
        content = template.read_text()
        assert "{% trans" in content


class TestTemplatesHaveCsrf:
    FORM_TEMPLATES = [
        DASHBOARDS_DIR / "dashboard_form.html",
        SETTINGS_DIR / "api_keys.html",
        SETTINGS_DIR / "bot_config.html",
    ]

    @pytest.mark.parametrize("template", FORM_TEMPLATES, ids=lambda t: str(t.name))
    def test_has_csrf_token(self, template: Path) -> None:
        content = template.read_text()
        assert "{% csrf_token %}" in content


class TestTemplatesNoForbiddenFrameworks:
    TEMPLATES = [
        DASHBOARDS_DIR / "dashboard_list.html",
        DASHBOARDS_DIR / "dashboard_form.html",
        SETTINGS_DIR / "index.html",
        SETTINGS_DIR / "api_keys.html",
        SETTINGS_DIR / "bot_config.html",
    ]

    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: str(t.name))
    def test_no_react_vue_alpine_jquery(self, template: Path) -> None:
        content = template.read_text().lower()
        for framework in ("react", "vue", "alpine", "jquery"):
            msg = f"{template.name} must not reference {framework}"
            assert framework not in content, msg


# ---------------------------------------------------------------------------
# Base Nav: Real URL Tags
# ---------------------------------------------------------------------------


class TestBaseNavRealURLs:
    @pytest.fixture(autouse=True)
    def _read_base(self) -> None:
        self.content = BASE_HTML.read_text()

    def test_dashboards_uses_url_tag(self) -> None:
        assert "{% url 'dashboard_list' %}" in self.content

    def test_settings_uses_url_tag(self) -> None:
        assert "{% url 'settings_index' %}" in self.content

    def test_no_hash_links_for_dashboards_or_settings(self) -> None:
        assert 'href="#"' not in self.content


# ---------------------------------------------------------------------------
# Static Safety: No SQL Writes on Read-Only Tables
# ---------------------------------------------------------------------------


class TestViewsStaticSafety:
    """Verify view/service files contain no raw SQL write statements."""

    WRITE_SQL = re.compile(
        r"""["'](?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\s""",
        re.IGNORECASE,
    )

    def test_dashboard_views_no_raw_sql_writes(self) -> None:
        source = Path(__file__).resolve().parent.parent / "apps" / "dashboards" / "views.py"
        content = source.read_text()
        assert self.WRITE_SQL.search(content) is None

    def test_settings_views_no_raw_sql_writes(self) -> None:
        source = Path(__file__).resolve().parent.parent / "apps" / "settings_app" / "views.py"
        content = source.read_text()
        assert self.WRITE_SQL.search(content) is None
