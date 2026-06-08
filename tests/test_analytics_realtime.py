"""Tests for the realtime analytics page — privacy-first aggregate pageviews.

Realtime is the sole survivor of the former "advanced pages" set; retention,
funnels, journeys, revenue, and engagement were removed because they require
persistent identifiers the product no longer collects.

Covers:
- URL routing for /realtime/ and the HTMX polling partial
- Login requirement (unauthenticated -> redirect to /login/)
- View + partial rendering with a mocked overview-data service
- Template structure: HTMX polling, active/recent pageview indicators
- Base-nav url tag, no forbidden JS frameworks
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from django.test import Client

from apps.core.models import MantecatoUser

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
WEBSITE_ID = "a0000000-0000-0000-0000-000000000001"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
BASE_HTML = TEMPLATES_DIR / "base.html"
ANALYTICS_DIR = TEMPLATES_DIR / "analytics"

# A realtime payload shaped like get_overview_data's return value: the partial
# template reads ``realtime`` (active count), ``current_pages``, ``recent_events``.
_REALTIME_DATA = {
    "realtime": {"count": 7},
    "current_pages": [{"urlPath": "/", "pageviews": 5}],
    "recent_events": [
        {
            "createdAt": "2025-01-15T10:30:00",
            "urlPath": "/",
            "country": "US",
            "browser": "Chrome",
        },
    ],
    "stats": {},
    "timeseries": [],
    "heatmap": [],
}


def _login_as_admin(client: Client) -> None:
    """Authenticate via ``client.force_login`` (no DB hit, no /login/ POST)."""
    from django.contrib.auth.signals import user_logged_in

    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)


def _patch_middleware_user(client: Client) -> MagicMock:
    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    patcher = patch(
        "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"
    )
    mock_process = patcher.start()

    def _set_user(request):
        request.user = user
    mock_process.side_effect = _set_user
    return patcher


# ---------------------------------------------------------------------------
# URL routing
# ---------------------------------------------------------------------------


class TestRealtimeRouting:
    def test_realtime_url_resolves(self) -> None:
        from django.urls import resolve

        assert resolve("/realtime/").url_name == "analytics_realtime"

    def test_realtime_partial_url_resolves(self) -> None:
        from django.urls import resolve

        assert resolve("/realtime/partial/").url_name == "analytics_realtime_partial"


# ---------------------------------------------------------------------------
# Login requirement
# ---------------------------------------------------------------------------


class TestRealtimeLoginRequired:
    def test_unauthenticated_redirects(self, client: Client) -> None:
        response = client.get("/realtime/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_authenticated_returns_200(self, client: Client) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with (
                patch(
                    "apps.analytics.views.resolve_websites_for_user",
                    return_value=[{"id": WEBSITE_ID, "name": "Test", "domain": "t.com"}],
                ),
                patch(
                    "apps.analytics.services.get_overview_data",
                    return_value=_REALTIME_DATA,
                ),
            ):
                response = client.get("/realtime/")
            assert response.status_code == 200
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# View + partial rendering
# ---------------------------------------------------------------------------


class TestRealtimeViewRendered:
    def _setup_client(self, client: Client) -> None:
        _login_as_admin(client)
        self._patcher = _patch_middleware_user(client)

    def teardown_method(self) -> None:
        if hasattr(self, "_patcher"):
            self._patcher.stop()

    @patch("apps.analytics.services.get_overview_data", return_value=_REALTIME_DATA)
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_realtime_renders_polling_and_count(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        response = client.get("/realtime/")
        content = response.content.decode()
        assert "hx-trigger" in content
        assert "every 5s" in content
        # The active-pageview count renders from the ``realtime`` context key.
        assert "7" in content

    @patch("apps.analytics.services.get_overview_data", return_value=_REALTIME_DATA)
    @patch("apps.analytics.partials.resolve_websites_for_user")
    def test_realtime_partial_renders_data(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        response = client.get(f"/realtime/partial/?website={WEBSITE_ID}")
        assert response.status_code == 200
        content = response.content.decode()
        assert "7" in content
        mock_data.assert_called_once()

    @patch("apps.analytics.services.get_overview_data")
    @patch("apps.analytics.partials.resolve_websites_for_user")
    def test_realtime_partial_rejects_inaccessible_website(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = []

        response = client.get(f"/realtime/partial/?website={WEBSITE_ID}")

        assert response.status_code == 200
        assert response.content == b""
        mock_data.assert_not_called()


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------


class TestRealtimeTemplates:
    def test_template_exists(self) -> None:
        assert (ANALYTICS_DIR / "realtime.html").is_file()

    def test_partial_exists(self) -> None:
        assert (ANALYTICS_DIR / "_realtime_data.html").is_file()

    def test_extends_base(self) -> None:
        content = (ANALYTICS_DIR / "realtime.html").read_text()
        assert '{% extends "base.html" %}' in content

    def test_uses_htmx_polling(self) -> None:
        content = (ANALYTICS_DIR / "realtime.html").read_text()
        assert "hx-trigger" in content
        assert "every" in content
        assert "5s" in content

    def test_partial_has_active_indicator(self) -> None:
        content = (ANALYTICS_DIR / "_realtime_data.html").read_text()
        assert "Active Pageviews" in content or "active" in content.lower()

    def test_partial_includes_pageview_stream(self) -> None:
        content = (ANALYTICS_DIR / "_realtime_data.html").read_text()
        assert "recent_events" in content or "current_pages" in content

    def test_nav_link_uses_url_tag(self) -> None:
        content = BASE_HTML.read_text()
        assert "{% url 'analytics_realtime' %}" in content

    def test_no_forbidden_frameworks(self) -> None:
        for name in ("realtime.html", "_realtime_data.html"):
            content = (ANALYTICS_DIR / name).read_text().lower()
            for fw in ("react", "vue", "alpine", "jquery"):
                assert fw not in content, f"{name} must not contain {fw}"
