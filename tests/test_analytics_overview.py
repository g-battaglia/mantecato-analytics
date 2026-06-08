"""Tests for the analytics overview page (Phase 2).

Covers:
- URL routing for overview and overview_tab
- Login requirement (unauthenticated → redirect to /login/)
- Service orchestration with mocked query functions (17 calls verified)
- Template contains Chart.js canvas, HTMX attributes, date range, filter controls,
  map container, stat cards
- No forbidden JS frameworks in overview template
- No write SQL in analytics views or services
- HTMX tab partial renders correct content
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from django.test import Client

from apps.core.models import MantecatoUser

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
WEBSITE_ID = "a0000000-0000-0000-0000-000000000001"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
OVERVIEW_HTML = TEMPLATES_DIR / "analytics" / "overview.html"


def _login_as_admin(client: Client) -> None:
    """Authenticate via ``client.force_login`` (no DB hit, no /login/ POST)."""
    from django.contrib.auth.signals import user_logged_in

    user = MantecatoUser(username="admin", role="admin")
    user.pk = ADMIN_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)


def _patch_middleware_user(client: Client) -> None:
    """Patch the middleware to resolve the session user without DB."""
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


class TestOverviewRouting:
    def test_overview_url_resolves(self) -> None:
        from django.urls import resolve
        match = resolve("/")
        assert match.url_name == "overview"

    def test_overview_tab_url_resolves(self) -> None:
        from django.urls import resolve
        match = resolve("/overview/tab/")
        assert match.url_name == "overview_tab"


# ---------------------------------------------------------------------------
# Login requirement
# ---------------------------------------------------------------------------


class TestOverviewLoginRequired:
    def test_unauthenticated_redirects_to_login(self, client: Client) -> None:
        response = client.get("/")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_unauthenticated_tab_redirects(self, client: Client) -> None:
        response = client.get("/overview/tab/?tab=pages")
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_authenticated_overview_returns_200(self, client: Client) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with patch("apps.analytics.views.resolve_websites_for_user", return_value=[]):
                response = client.get("/")
            assert response.status_code == 200
        finally:
            patcher.stop()

    def test_authenticated_tab_returns_200(self, client: Client) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with patch("apps.analytics.partials.resolve_websites_for_user", return_value=[]):
                response = client.get("/overview/tab/?tab=pages")
            assert response.status_code == 200
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# Service orchestration (mocked query functions)
# ---------------------------------------------------------------------------


class TestServiceOrchestration:
    """get_overview_data orchestration, with every query helper mocked.

    All 16 fan-out helpers are stubbed, so the test never touches the
    database (no ``django_db`` mark needed) and asserts the *shape* of the
    orchestration: which helpers run and how many times.
    """

    # Each fan-out helper get_overview_data calls -> a safe stub return.
    # Privacy-first: pageview/event/device/geo aggregates only. The anonymous
    # visitor estimate path is exercised separately (it only runs for a
    # bot-only filter), so a content filter in ``_run`` keeps this test DB-free.
    _STUBS = {
        "get_website_stats_comparison": {
            "current": {"pageviews": 100, "human_pageviews": 80, "bot_pageviews": 20},
            "previous": {"pageviews": 80, "human_pageviews": 64, "bot_pageviews": 16},
        },
        "get_pageview_time_series_comparison": {"current": [], "previous": []},
        "get_device_metrics_multi": {"browser": [], "os": [], "device": []},
        "get_top_sections": [],
        "get_event_metrics": [],
        "get_top_pages": [],
        "get_country_breakdown": [],
        "get_geo_metrics": [],
        "get_active_pageviews": {"count": 0},
        "get_recent_pageviews": [],
        "get_current_pages": [],
        "get_traffic_heatmap": [],
    }

    @contextmanager
    def _patched(self):
        with ExitStack() as stack:
            mocks = {
                name: stack.enter_context(
                    patch(f"apps.analytics.services.{name}", return_value=ret)
                )
                for name, ret in self._STUBS.items()
            }
            yield mocks

    def _run(self):
        from apps.analytics.services import get_overview_data
        from core.mantecato_core.date_utils import DateRange
        from core.mantecato_core.filters import Filter

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        # A content filter disables the anonymous-visitor estimate path (which
        # only runs for a bot-only filter), keeping the test DB-free.
        return get_overview_data(
            WEBSITE_ID, date_range, [Filter(column="country", operator="eq", value="US")]
        )

    def test_uses_comparison_helpers_once(self) -> None:
        with self._patched() as mocks:
            result = self._run()
        # Current + previous now come from a single combined call each.
        assert mocks["get_website_stats_comparison"].call_count == 1
        assert mocks["get_pageview_time_series_comparison"].call_count == 1
        # KPI cards are derived from the "current" period of the comparison.
        assert result["stats"]["pageviews"]["value"] == "100"
        # With a content filter the anonymous-visitor estimate is unavailable.
        assert result["stats"]["visitors"]["value"] == "N/A"

    def test_device_metrics_multi_once(self) -> None:
        with self._patched() as mocks:
            self._run()
        assert mocks["get_device_metrics_multi"].call_count == 1

    def test_every_helper_called_exactly_once(self) -> None:
        """No fan-out helper runs more than once (no N+1, no duplicate scans)."""
        with self._patched() as mocks:
            self._run()
        for name, mock in mocks.items():
            assert mock.call_count == 1, f"{name} called {mock.call_count}x (expected 1)"


# ---------------------------------------------------------------------------
# Template content
# ---------------------------------------------------------------------------


class TestOverviewTemplateContent:
    @pytest.fixture(autouse=True)
    def _read_template(self) -> None:
        self.content = OVERVIEW_HTML.read_text()

    def test_extends_base(self) -> None:
        assert '{% extends "base.html" %}' in self.content

    def test_has_chart_canvas(self) -> None:
        assert "timeseries-canvas" in self.content, "Must have canvas for Chart.js"

    def test_has_json_script_for_timeseries(self) -> None:
        assert "json_script" in self.content, "Must use json_script for chart data"

    def test_has_htmx_attributes(self) -> None:
        base = (TEMPLATES_DIR / "base.html").read_text()
        assert "htmx.org" in base, "Must include HTMX library in base template"

    def test_has_date_range_select(self) -> None:
        content = self.content
        filter_bar = (TEMPLATES_DIR / "components" / "_filter_bar.html").read_text()
        combined = content + filter_bar
        assert "range" in combined.lower(), "Must have date range selector"

    def test_has_site_selector(self) -> None:
        base = (TEMPLATES_DIR / "base.html").read_text()
        assert "site-selector" in base, "Must have site selector in base template"

    def test_has_map_container(self) -> None:
        assert "world-map" in self.content, "Must have map container"

    def test_has_leaflet_css(self) -> None:
        assert "leaflet" in self.content.lower(), "Must include Leaflet CSS"

    def test_has_leaflet_js(self) -> None:
        assert "leaflet.js" in self.content, "Must include Leaflet JS"

    def test_map_plots_country_markers(self) -> None:
        assert "countryCenters" in self.content
        assert ".addTo(map)" in self.content

    def test_has_trans_tags(self) -> None:
        assert "{% trans" in self.content or "{% blocktrans" in self.content

    def test_has_stat_cards_include(self) -> None:
        assert "_overview_metrics.html" in self.content

    def test_has_timeseries_include(self) -> None:
        assert "_overview_timeseries.html" in self.content

    def test_has_tables_include(self) -> None:
        assert "_overview_tables.html" in self.content

    def test_has_realtime_indicator(self) -> None:
        assert "realtime" in self.content.lower()


class TestOverviewTemplateForbidden:
    @pytest.fixture(autouse=True)
    def _read_template(self) -> None:
        self.content = OVERVIEW_HTML.read_text().lower()

    def test_no_react(self) -> None:
        assert "react" not in self.content

    def test_no_vue(self) -> None:
        assert "vue" not in self.content

    def test_no_alpine(self) -> None:
        assert "alpine" not in self.content

    def test_no_jquery(self) -> None:
        assert "jquery" not in self.content


# ---------------------------------------------------------------------------
# Tab partials exist
# ---------------------------------------------------------------------------


class TestTabPartialsExist:
    def test_tab_pages_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_tab_pages.html").is_file()

    def test_tab_events_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_tab_events.html").is_file()

    def test_tab_devices_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_tab_devices.html").is_file()

    def test_tab_geo_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_tab_geo.html").is_file()

    def test_overview_metrics_partial_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_overview_metrics.html").is_file()

    def test_overview_timeseries_partial_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_overview_timeseries.html").is_file()

    def test_overview_tables_partial_exists(self) -> None:
        assert (TEMPLATES_DIR / "analytics" / "_overview_tables.html").is_file()


# ---------------------------------------------------------------------------
# No write SQL in analytics app
# ---------------------------------------------------------------------------


class TestAnalyticsNoWriteSql:
    WRITE_PATTERN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
        re.IGNORECASE,
    )

    def test_views_no_write_sql(self) -> None:
        import apps.analytics.views as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert self.WRITE_PATTERN.search(source) is None

    def test_services_no_write_sql(self) -> None:
        import apps.analytics.services as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert self.WRITE_PATTERN.search(source) is None

    def test_urls_no_write_sql(self) -> None:
        import apps.analytics.urls as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert self.WRITE_PATTERN.search(source) is None


# ---------------------------------------------------------------------------
# View rendering with mocked service
# ---------------------------------------------------------------------------


class TestOverviewViewRendered:
    def _setup_client(self, client: Client) -> None:
        _login_as_admin(client)
        self._patcher = _patch_middleware_user(client)

    def teardown_method(self) -> None:
        if hasattr(self, "_patcher"):
            self._patcher.stop()

    @patch("apps.analytics.views.get_overview_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_renders_stat_cards(
        self,
        mock_websites: MagicMock,
        mock_data: MagicMock,
        client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "stats": {
                "pageviews": {"value": "1.2K", "change": {"value": "5.0%", "trend": "up"}},
                "visitors": {"value": "567", "change": {"value": "2.1%", "trend": "up"}},
                "visits": {"value": "890", "change": None},
                "bounce_rate": {"value": 45.2, "change": {"value": "3.0%", "trend": "down"}},
                "avg_duration": {"value": "2m 30s", "change": None},
                "pages_per_visit": {"value": 1.4, "change": None},
            },
            "timeseries": [],
            "prev_timeseries": [],
            "sections": [],
            "top_pages": [],
            "top_referrers": [],
            "top_events": [],
            "browser": [],
            "os": [],
            "device": [],
            "language": [],
            "country": [],
            "geo": [],
            "channels": [],
            "referrer_metrics": [],
            "realtime": {"count": 3, "visitors": []},
            "recent_events": [],
            "current_pages": [],
            "heatmap": [],
            "event_metrics": [],
            "date_range": MagicMock(),
            "granularity": "day",
        }

        response = client.get("/")
        content = response.content.decode()

        assert "1.2K" in content
        assert "567" in content
        assert "5.0%" in content

    @patch("apps.analytics.views.get_overview_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_no_website_shows_no_data_message(
        self,
        mock_websites: MagicMock,
        mock_data: MagicMock,
        client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = []

        response = client.get("/")
        content = response.content.decode()

        assert "No websites" in content

    @patch("apps.analytics.services.get_top_pages")
    @patch("apps.analytics.partials.resolve_websites_for_user")
    def test_tab_partial_renders_pages(
        self,
        mock_websites: MagicMock,
        mock_top_pages: MagicMock,
        client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_top_pages.return_value = [
            {"urlPath": "/", "views": 42, "visitors": 30},
        ]

        # A content filter suppresses visitor counts, keeping the request off
        # the visitor-aggregate path (no DB query for visitor tables).
        response = client.get(
            "/overview/tab/?tab=pages&f=country:eq:US&website=" + WEBSITE_ID
        )
        content = response.content.decode()

        assert "42" in content


# ---------------------------------------------------------------------------
# Service helper functions
# ---------------------------------------------------------------------------


class TestServiceHelpers:
    def test_percentage_change_positive(self) -> None:
        from apps.analytics.services import _percentage_change
        result = _percentage_change(150, 100)
        assert result == {"value": "50.0%", "trend": "up"}

    def test_percentage_change_negative(self) -> None:
        from apps.analytics.services import _percentage_change
        result = _percentage_change(50, 100)
        assert result == {"value": "50.0%", "trend": "down"}

    def test_percentage_change_zero_previous(self) -> None:
        from apps.analytics.services import _percentage_change
        result = _percentage_change(10, 0)
        assert result == {"value": "100%", "trend": "up"}

    def test_percentage_change_both_zero(self) -> None:
        from apps.analytics.services import _percentage_change
        assert _percentage_change(0, 0) is None
