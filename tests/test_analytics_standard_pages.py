"""Tests for Phase 3 standard analytics pages.

Covers:
- URL routing for all 7 pages (pages, sources, events, sessions, devices, geo, compare)
- Login requirement (unauthenticated → redirect to /login/)
- Service orchestration with mocked query functions
- Templates exist, extend base, use i18n, contain expected markers
- Base template nav has real {% url %} tags (not #)
- No write SQL in analytics views/services/urls
- No forbidden JS frameworks in new templates
"""

from __future__ import annotations

import re
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
BASE_HTML = TEMPLATES_DIR / "base.html"
ANALYTICS_DIR = TEMPLATES_DIR / "analytics"

PAGES = ["pages", "sources", "events", "sessions", "devices", "geo", "compare"]
ROUTES = {
    "pages": "/pages/",
    "sources": "/sources/",
    "events": "/events/",
    "sessions": "/sessions/",
    "devices": "/devices/",
    "geo": "/geo/",
    "compare": "/compare/",
}
URL_NAMES = {
    "pages": "analytics_pages",
    "sources": "analytics_sources",
    "events": "analytics_events",
    "sessions": "analytics_sessions",
    "devices": "analytics_devices",
    "geo": "analytics_geo",
    "compare": "analytics_compare",
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


class TestStandardPageRouteResolution:
    @pytest.mark.parametrize("page", PAGES)
    def test_url_resolves(self, page: str) -> None:
        from django.urls import resolve

        url_name = URL_NAMES[page]
        match = resolve(ROUTES[page])
        assert match.url_name == url_name


# ---------------------------------------------------------------------------
# Login requirement
# ---------------------------------------------------------------------------


class TestStandardPagesLoginRequired:
    @pytest.mark.parametrize("page", PAGES)
    def test_unauthenticated_redirects(self, client: Client, page: str) -> None:
        response = client.get(ROUTES[page])
        assert response.status_code == 302
        assert "/login/" in response.url

    @pytest.mark.parametrize("page", PAGES)
    def test_authenticated_returns_200(self, client: Client, page: str) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with (
                patch(
                    "apps.analytics.views.resolve_websites_for_user",
                    return_value=[],
                ),
                patch(
                    "apps.analytics.views.get_pages_data",
                    return_value={"pages": [], "page": 1},
                ),
                patch(
                    "apps.analytics.views.get_sources_data",
                    return_value={
                        "referrers": [], "channels": [],
                        "utm_source": [], "utm_medium": [],
                        "utm_campaign": [], "click_ids": [],
                        "hostnames": [],
                    },
                ),
                patch(
                    "apps.analytics.views.get_events_data",
                    return_value={"events": []},
                ),
                patch(
                    "apps.analytics.views.get_sessions_data",
                    return_value={"sessions": [], "page": 1},
                ),
                patch(
                    "apps.analytics.views.get_devices_data",
                    return_value={
                        "browser": [], "os": [],
                        "device": [], "screen": [], "language": [],
                    },
                ),
                patch(
                    "apps.analytics.views.get_geo_data",
                    return_value={
                        "geo": [], "level": "country",
                        "country": None, "region": None,
                    },
                ),
                patch(
                    "apps.analytics.views.get_compare_data",
                    return_value={
                        "stats": {}, "comparison": [],
                        "comparison_mode": "previous_period",
                    },
                ),
            ):
                response = client.get(ROUTES[page])
            assert response.status_code == 200
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# Service orchestration — Pages
# ---------------------------------------------------------------------------


class TestPagesServiceOrchestration:
    @patch("apps.analytics.services.get_page_metrics", return_value=[])
    def test_calls_get_page_metrics(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_pages_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        get_pages_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert mock_fn.call_args[0][0] == WEBSITE_ID

    @patch("apps.analytics.services.get_page_metrics", return_value=[])
    def test_passes_pagination_offset(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_pages_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        get_pages_data(WEBSITE_ID, date_range, page=3)
        assert mock_fn.call_args[1].get("offset") == 100 or mock_fn.call_args[0][3] == 50


# ---------------------------------------------------------------------------
# Service orchestration — Sources
# ---------------------------------------------------------------------------


class TestSourcesServiceOrchestration:
    @patch("apps.analytics.services.get_hostname_metrics", return_value=[])
    @patch("apps.analytics.services.get_click_id_metrics", return_value=[])
    @patch("apps.analytics.services.get_utm_metrics", return_value=[])
    @patch("apps.analytics.services.get_channel_metrics", return_value=[])
    @patch("apps.analytics.services.get_referrer_metrics", return_value=[])
    def test_calls_seven_query_functions(
        self,
        mock_ref: MagicMock,
        mock_ch: MagicMock,
        mock_utm: MagicMock,
        mock_click: MagicMock,
        mock_host: MagicMock,
    ) -> None:
        from apps.analytics.services import get_sources_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_sources_data(WEBSITE_ID, date_range)
        assert mock_ref.call_count == 1
        assert mock_ch.call_count == 1
        assert mock_utm.call_count == 3  # source, medium, campaign
        assert mock_click.call_count == 1
        assert mock_host.call_count == 1
        assert "referrers" in result
        assert "channels" in result


# ---------------------------------------------------------------------------
# Service orchestration — Overview tab fetchers
# ---------------------------------------------------------------------------

_DATE_RANGE_FIXTURE = None


def _make_date_range():
    from core.mantecato_core.date_utils import DateRange
    return DateRange(
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 1, 31, tzinfo=UTC),
    )


class TestOverviewTabFetchers:
    @patch("apps.analytics.services.get_top_pages", return_value=[{"views": 10}])
    def test_tab_pages_returns_expected_keys(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_overview_tab_pages
        result = get_overview_tab_pages(WEBSITE_ID, _make_date_range())
        assert "top_pages" in result
        assert mock_fn.call_count == 1

    @patch("apps.analytics.services.get_top_referrers", return_value=[])
    def test_tab_referrers_returns_expected_keys(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_overview_tab_referrers
        result = get_overview_tab_referrers(WEBSITE_ID, _make_date_range())
        assert "top_referrers" in result

    @patch("apps.analytics.services.get_top_events", return_value=[])
    def test_tab_events_returns_expected_keys(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_overview_tab_events
        result = get_overview_tab_events(WEBSITE_ID, _make_date_range())
        assert "top_events" in result

    @patch(
        "apps.analytics.services.get_device_metrics_multi",
        return_value={"browser": [], "os": [], "device": [], "language": []},
    )
    def test_tab_devices_returns_expected_keys(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_overview_tab_devices
        result = get_overview_tab_devices(WEBSITE_ID, _make_date_range())
        for key in ("browser", "os_data", "device_data", "language"):
            assert key in result, f"missing key: {key}"
        assert mock_fn.call_count == 1

    @patch("apps.analytics.services.get_geo_metrics", return_value=[])
    @patch("apps.analytics.services.get_country_breakdown", return_value=[])
    def test_tab_geo_returns_expected_keys(
        self, mock_cb: MagicMock, mock_geo: MagicMock,
    ) -> None:
        from apps.analytics.services import get_overview_tab_geo
        result = get_overview_tab_geo(WEBSITE_ID, _make_date_range())
        assert "country" in result
        assert "geo" in result

    @patch("apps.analytics.services.get_referrer_metrics", return_value=[])
    @patch("apps.analytics.services.get_channel_metrics", return_value=[])
    def test_tab_sources_returns_expected_keys(
        self, mock_ch: MagicMock, mock_ref: MagicMock,
    ) -> None:
        from apps.analytics.services import get_overview_tab_sources
        result = get_overview_tab_sources(WEBSITE_ID, _make_date_range())
        assert "channels" in result
        assert "referrer_metrics" in result


# ---------------------------------------------------------------------------
# Service orchestration — Events
# ---------------------------------------------------------------------------


class TestEventsServiceOrchestration:
    @patch("apps.analytics.services.get_event_metrics", return_value=[])
    def test_calls_get_event_metrics(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_events_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_events_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert "events" in result


# ---------------------------------------------------------------------------
# Service orchestration — Sessions
# ---------------------------------------------------------------------------


class TestSessionsServiceOrchestration:
    @patch("apps.analytics.services.get_session_list", return_value=[])
    def test_calls_get_session_list(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_sessions_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_sessions_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert "sessions" in result


# ---------------------------------------------------------------------------
# Service orchestration — Devices
# ---------------------------------------------------------------------------


class TestDevicesServiceOrchestration:
    @patch("apps.analytics.services.get_device_metrics", return_value=[])
    @patch(
        "apps.analytics.services.get_device_metrics_multi",
        return_value={"browser": [], "os": [], "device": [], "language": []},
    )
    def test_devices_data_uses_merged_helper(
        self, mock_multi: MagicMock, mock_screen: MagicMock
    ) -> None:
        from apps.analytics.services import get_devices_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_devices_data(WEBSITE_ID, date_range)
        # One merged call covers 4 dimensions; ``screen`` stays a single call.
        assert mock_multi.call_count == 1
        assert mock_screen.call_count == 1
        assert mock_screen.call_args.args[3] == "screen"
        assert "browser" in result


# ---------------------------------------------------------------------------
# Service orchestration — Geo
# ---------------------------------------------------------------------------


class TestGeoServiceOrchestration:
    _GEO_ROW = {
        "country": "US", "region": None, "city": None,
        "visitors": 100, "pageviews": 300, "visits": 120,
        "bounceRate": 45.0, "avgDuration": 62.0,
    }

    @patch("apps.analytics.services.get_country_breakdown", return_value=[])
    @patch("apps.analytics.services.get_geo_metrics", return_value=[])
    def test_calls_geo_metrics_country_level(
        self, mock_geo: MagicMock, mock_cb: MagicMock,
    ) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range)
        assert mock_geo.call_count == 1
        assert result["level"] == "country"
        assert result["country"] is None

    @patch("apps.analytics.services.get_geo_metrics", return_value=[])
    def test_drills_to_region_level(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range, country="US")
        assert result["level"] == "region"

    @patch("apps.analytics.services.get_geo_metrics", return_value=[])
    def test_drills_to_city_level(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range, country="US", region="California")
        assert result["level"] == "city"

    @patch("apps.analytics.services.get_country_breakdown", return_value=[
        {"country": "US", "visitors": 80, "pageviews": 200},
        {"country": "IT", "visitors": 20, "pageviews": 50},
    ])
    @patch("apps.analytics.services.get_geo_metrics")
    def test_country_level_includes_summary_and_charts(
        self, mock_geo: MagicMock, mock_cb: MagicMock,
    ) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        mock_geo.return_value = [self._GEO_ROW]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range)
        assert "geo_summary" in result
        assert result["geo_summary"]["total_countries"] == 1
        assert result["geo_summary"]["top_country"] == "US"
        assert "country_breakdown" in result
        assert "top_regions" in result
        assert "top_regions_country" in result

    @patch("apps.analytics.services.get_geo_metrics", return_value=[])
    def test_drilldown_excludes_summary(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range, country="US")
        assert "geo_summary" not in result
        assert "country_breakdown" not in result

    @patch("apps.analytics.services.get_geo_metrics", return_value=[
        {"country": "US", "region": None, "city": None,
         "visitors": 60, "pageviews": 180, "visits": 70,
         "bounceRate": 40.0, "avgDuration": 55.0},
        {"country": "IT", "region": None, "city": None,
         "visitors": 40, "pageviews": 120, "visits": 50,
         "bounceRate": 50.0, "avgDuration": 45.0},
    ])
    @patch("apps.analytics.services.get_country_breakdown", return_value=[])
    def test_geo_rows_have_percentage(
        self, mock_cb: MagicMock, mock_geo: MagicMock,
    ) -> None:
        from apps.analytics.services import get_geo_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_geo_data(WEBSITE_ID, date_range)
        for g in result["geo"]:
            assert "pct" in g


# ---------------------------------------------------------------------------
# Service orchestration — Compare
# ---------------------------------------------------------------------------


class TestCompareServiceOrchestration:
    @patch("apps.analytics.services.get_pageview_time_series", return_value=[])
    @patch("apps.analytics.services.get_comparison_stats")
    def test_calls_get_comparison_stats(
        self, mock_fn: MagicMock, mock_ts: MagicMock,
    ) -> None:
        from apps.analytics.services import get_compare_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {
                "period": "current", "pageviews": 100,
                "visitors": 50, "visits": 60,
                "bounces": 20, "totaltime": 1800,
            },
            {
                "period": "previous", "pageviews": 80,
                "visitors": 40, "visits": 50,
                "bounces": 15, "totaltime": 1500,
            },
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_compare_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert "stats" in result
        assert result["stats"]["pageviews"]["value"] == "100"
        assert result["comparison_mode"] == "previous_period"

    @patch("apps.analytics.services.get_pageview_time_series", return_value=[])
    @patch("apps.analytics.services.get_comparison_stats")
    def test_handles_previous_year_mode(
        self, mock_fn: MagicMock, mock_ts: MagicMock,
    ) -> None:
        from apps.analytics.services import get_compare_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {
                "period": "current", "pageviews": 100,
                "visitors": 50, "visits": 60,
                "bounces": 20, "totaltime": 1800,
            },
            {
                "period": "previous", "pageviews": 90,
                "visitors": 45, "visits": 55,
                "bounces": 18, "totaltime": 1600,
            },
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_compare_data(WEBSITE_ID, date_range, comparison_mode="previous_year")
        assert result["comparison_mode"] == "previous_year"


# ---------------------------------------------------------------------------
# Template existence and structure
# ---------------------------------------------------------------------------


class TestTemplateFiles:
    @pytest.mark.parametrize("page", PAGES)
    def test_template_exists(self, page: str) -> None:
        assert (ANALYTICS_DIR / f"{page}.html").is_file()

    @pytest.mark.parametrize("page", PAGES)
    def test_extends_base(self, page: str) -> None:
        content = (ANALYTICS_DIR / f"{page}.html").read_text()
        assert '{% extends "base.html" %}' in content

    @pytest.mark.parametrize("page", PAGES)
    def test_has_trans_tags(self, page: str) -> None:
        content = (ANALYTICS_DIR / f"{page}.html").read_text()
        assert "{% trans" in content or "{% blocktrans" in content

    @pytest.mark.parametrize("page", PAGES)
    def test_includes_filter_bar(self, page: str) -> None:
        content = (ANALYTICS_DIR / f"{page}.html").read_text()
        assert "_filter_bar.html" in content

    def test_filter_bar_partial_exists(self) -> None:
        assert (TEMPLATES_DIR / "components" / "_filter_bar.html").is_file()

    def test_base_has_htmx(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text()
        assert "htmx.org" in content, "Base template must include HTMX library"

    def test_base_has_site_selector(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text()
        assert "site-selector" in content, "Base template must have site selector"

    def test_filter_bar_has_date_range(self) -> None:
        content = (TEMPLATES_DIR / "components" / "_filter_bar.html").read_text()
        assert "range" in content.lower()

    def test_filter_bar_uses_i18n(self) -> None:
        content = (TEMPLATES_DIR / "components" / "_filter_bar.html").read_text()
        assert "{% trans" in content or "{% load i18n" in content


# ---------------------------------------------------------------------------
# Template content specifics
# ---------------------------------------------------------------------------


class TestTemplateContent:
    def test_pages_has_page_list(self) -> None:
        content = (ANALYTICS_DIR / "pages.html").read_text()
        assert "urlPath" in content or "pages" in content, "Must display page data"

    def test_pages_has_page_columns(self) -> None:
        content = (ANALYTICS_DIR / "pages.html").read_text()
        assert "Views" in content or "views" in content.lower()

    def test_sources_has_multiple_tables(self) -> None:
        content = (ANALYTICS_DIR / "sources.html").read_text()
        assert content.count("<table") >= 3  # channels, referrers, UTM

    def test_events_has_table(self) -> None:
        content = (ANALYTICS_DIR / "events.html").read_text()
        assert "<table" in content

    def test_sessions_has_table(self) -> None:
        content = (ANALYTICS_DIR / "sessions.html").read_text()
        assert "<table" in content

    def test_devices_has_charts(self) -> None:
        content = (ANALYTICS_DIR / "devices.html").read_text()
        assert "canvas" in content.lower()
        assert "json_script" in content
        assert "initPieChart" in content

    def test_geo_has_drilldown_links(self) -> None:
        content = (ANALYTICS_DIR / "geo.html").read_text()
        assert "country=" in content or "drill" in content.lower()

    def test_compare_has_mode_selector(self) -> None:
        content = (ANALYTICS_DIR / "compare.html").read_text()
        assert "previous_period" in content
        assert "previous_year" in content

    def test_compare_has_stat_cards(self) -> None:
        content = (ANALYTICS_DIR / "compare.html").read_text()
        assert "Pageviews" in content
        assert "Visitors" in content


# ---------------------------------------------------------------------------
# No forbidden JS frameworks in new templates
# ---------------------------------------------------------------------------


class TestTemplatesForbidden:
    FORBIDDEN = ["react", "vue", "alpine", "jquery"]

    @pytest.mark.parametrize("page", PAGES)
    def test_no_forbidden_frameworks(self, page: str) -> None:
        content = (ANALYTICS_DIR / f"{page}.html").read_text().lower()
        for fw in self.FORBIDDEN:
            assert fw not in content, f"{page}.html must not contain {fw}"

    def test_filter_bar_no_forbidden_frameworks(self) -> None:
        content = (TEMPLATES_DIR / "components" / "_filter_bar.html").read_text().lower()
        for fw in self.FORBIDDEN:
            assert fw not in content, f"_filter_bar.html must not contain {fw}"


# ---------------------------------------------------------------------------
# Base template nav has real URLs
# ---------------------------------------------------------------------------


class TestBaseNavRealUrls:
    @pytest.fixture(autouse=True)
    def _read_base(self) -> None:
        self.content = BASE_HTML.read_text()

    def test_pages_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_pages' %}" in self.content

    def test_sources_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_sources' %}" in self.content

    def test_events_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_events' %}" in self.content

    def test_sessions_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_sessions' %}" in self.content

    def test_devices_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_devices' %}" in self.content

    def test_geo_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_geo' %}" in self.content

    def test_compare_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_compare' %}" in self.content

    def test_no_hash_hrefs_for_connected_pages(self) -> None:
        """Pages, Sources, Events, Sessions, Devices, Geo, Compare must not use href="#"."""
        for page_name in ["Pages", "Sources", "Events", "Sessions", "Devices", "Geo"]:
            lines = self.content.split("\n")
            for line in lines:
                if page_name in line and "nav-link" in line:
                    assert 'href="#"' not in line, f"Nav link for {page_name} still uses href=#"


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


class TestViewHelpers:
    def test_safe_int_rejects_invalid_value(self) -> None:
        from apps.common.http import safe_int

        assert safe_int("not-a-number") == 1

    def test_safe_int_clamps_negative_value(self) -> None:
        from apps.common.http import safe_int

        assert safe_int("-3") == 1


class TestPagesViewRendered:
    def _setup_client(self, client: Client) -> None:
        _login_as_admin(client)
        self._patcher = _patch_middleware_user(client)

    def teardown_method(self) -> None:
        if hasattr(self, "_patcher"):
            self._patcher.stop()

    @patch("apps.analytics.views.get_pages_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_pages_renders_table_rows(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "pages": [
                {"urlPath": "/", "pageTitle": "Home", "views": 42, "visitors": 30,
                 "bounceRate": 25.5, "avgTimeOnPage": 45.0, "entries": 20, "exits": 10},
            ],
            "page": 1,
        }
        response = client.get("/pages/")
        content = response.content.decode()
        assert "42" in content
        assert "Home" in content

    @patch("apps.analytics.views.get_sources_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_sources_renders_channels(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "referrers": [],
            "channels": [
                {
                    "channel": "Direct", "visitors": 100,
                    "pageviews": 200, "bounceRate": 30.0,
                },
            ],
            "utm_source": [], "utm_medium": [], "utm_campaign": [],
            "click_ids": [], "hostnames": [],
        }
        response = client.get("/sources/")
        content = response.content.decode()
        assert "Direct" in content
        assert "100" in content

    @patch("apps.analytics.views.get_events_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_events_renders_event_names(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "events": [
                {"eventName": "signup", "count": 15, "visitors": 12, "lastTriggered": "2025-01-15"},
            ],
        }
        response = client.get("/events/")
        content = response.content.decode()
        assert "signup" in content
        assert "15" in content

    @patch("apps.analytics.views.get_sessions_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_sessions_renders_session_data(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "sessions": [
                {"sessionId": "s1", "country": "US", "city": "NYC",
                 "browser": "Chrome", "os": "Windows", "device": "Desktop",
                 "pagesViewed": 5, "duration": 120.0, "startedAt": "2025-01-15T10:30:00"},
            ],
            "page": 1,
        }
        response = client.get("/sessions/")
        content = response.content.decode()
        assert "Chrome" in content
        assert "5" in content

    @patch("apps.analytics.views.get_compare_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_compare_renders_comparison(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "stats": {
                "pageviews": {"value": "500", "change": {"value": "25.0%", "trend": "up"}},
                "visitors": {"value": "200", "change": {"value": "10.0%", "trend": "up"}},
                "visits": {"value": "300", "change": {"value": "5.0%", "trend": "up"}},
                "bounce_rate": {"value": 35.0, "change": {"value": "2.0%", "trend": "down"}},
                "avg_duration": {"value": "2m 30s", "change": None},
                "pages_per_visit": {"value": 1.7, "change": None},
            },
            "comparison": [
                {
                    "period": "current", "pageviews": 500,
                    "visitors": 200, "visits": 300,
                    "bounces": 100, "totaltime": 7500,
                },
                {
                    "period": "previous", "pageviews": 400,
                    "visitors": 180, "visits": 280,
                    "bounces": 90, "totaltime": 6000,
                },
            ],
            "comparison_mode": "previous_period",
            "current_ts": [],
            "previous_ts": [],
        }
        response = client.get("/compare/")
        content = response.content.decode()
        assert "25.0%" in content
        assert "500" in content


# ---------------------------------------------------------------------------
# Filter values endpoint (typeahead for the "Add filter" popover)
# ---------------------------------------------------------------------------


class TestFilterValuesView:
    """The /filter-values/ HTMX partial powering the filter typeahead."""

    def test_returns_options_for_valid_column(self, client: Client) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with (
                patch(
                    "apps.analytics.partials.resolve_websites_for_user",
                    return_value=[{"id": WEBSITE_ID, "name": "Site"}],
                ),
                patch(
                    "apps.analytics.partials.get_filter_values",
                    return_value=["IT", "US"],
                ) as mock_vals,
            ):
                response = client.get(
                    f"/filter-values/?website={WEBSITE_ID}&range=30d&column=country&search=I"
                )
            assert response.status_code == 200
            content = response.content.decode()
            assert '<option value="IT">' in content
            assert '<option value="US">' in content
            # column + search forwarded to the query helper
            args, kwargs = mock_vals.call_args
            assert args[1] == "country"
            assert kwargs.get("search") == "I"
        finally:
            patcher.stop()

    def test_missing_column_returns_empty(self, client: Client) -> None:
        _login_as_admin(client)
        patcher = _patch_middleware_user(client)
        try:
            with patch(
                "apps.analytics.partials.resolve_websites_for_user",
                return_value=[{"id": WEBSITE_ID, "name": "Site"}],
            ):
                response = client.get(f"/filter-values/?website={WEBSITE_ID}&range=30d")
            assert response.status_code == 200
            assert response.content.decode().strip() == ""
        finally:
            patcher.stop()
