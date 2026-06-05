"""Tests for Phase 4 advanced analytics pages.

Covers:
- URL routing for all 6 pages (retention, funnels, journeys, revenue, engagement, realtime)
- Login requirement (unauthenticated -> redirect to /login/)
- Service orchestration with mocked query functions
- Templates exist, extend base, use i18n, contain expected markers
- Base template nav has real {% url %} tags (not #) for Phase 4 pages
- No write SQL in analytics views/services/urls
- No forbidden JS frameworks in new templates
- Realtime template uses HTMX polling
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

PAGES = ["retention", "funnels", "journeys", "revenue", "engagement", "realtime"]
ROUTES = {
    "retention": "/retention/",
    "funnels": "/funnels/",
    "journeys": "/journeys/",
    "revenue": "/revenue/",
    "engagement": "/engagement/",
    "realtime": "/realtime/",
}
URL_NAMES = {
    "retention": "analytics_retention",
    "funnels": "analytics_funnels",
    "journeys": "analytics_journeys",
    "revenue": "analytics_revenue",
    "engagement": "analytics_engagement",
    "realtime": "analytics_realtime",
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


class TestAdvancedPageRouteResolution:
    @pytest.mark.parametrize("page", PAGES)
    def test_url_resolves(self, page: str) -> None:
        from django.urls import resolve

        match = resolve(ROUTES[page])
        assert match.url_name == URL_NAMES[page]


# ---------------------------------------------------------------------------
# Login requirement
# ---------------------------------------------------------------------------


class TestAdvancedPagesLoginRequired:
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
                    return_value=[{"id": WEBSITE_ID, "name": "Test", "domain": "t.com"}],
                ),
                patch(
                    "apps.analytics.views.get_retention_data",
                    return_value={"cohorts": [], "granularity": "week"},
                ),
                patch(
                    "apps.analytics.views.get_funnels_data",
                    return_value={
                        "funnel_steps": [], "steps_config": [],
                        "funnel_chart_data": {"labels": [], "datasets": []},
                    },
                ),
                patch(
                    "apps.analytics.views.get_journeys_data",
                    return_value={
                        "journeys": [], "sankey": {"nodes": [], "links": []},
                        "mode": "sections", "conversions": [],
                    },
                ),
                patch(
                    "apps.analytics.views.get_entry_exit_data",
                    return_value={"entry_pages": [], "exit_pages": []},
                ),
                patch(
                    "apps.analytics.views.get_revenue_data",
                    return_value={
                        "summary": {
                            "totalRevenue": 0, "transactions": 0,
                            "uniqueCustomers": 0, "arpu": 0,
                        },
                        "time_series": [], "by_event": [], "by_country": [],
                        "revenue_chart_data": {"labels": [], "datasets": []},
                        "event_chart_data": {"labels": [], "datasets": []},
                    },
                ),
                patch(
                    "apps.analytics.views.get_engagement_data",
                    return_value={
                        "distribution": [], "percentiles": {},
                        "duration_by_page": [], "bounce_by_page": [], "bounce_by_source": [],
                        "distribution_chart_data": {"labels": [], "datasets": []},
                        "bounce_chart_data": {"labels": [], "datasets": []},
                    },
                ),
                patch(
                    "apps.analytics.views.get_heatmap_data",
                    return_value={"grid": [[0] * 24 for _ in range(7)], "max_val": 0},
                ),
                patch(
                    "apps.analytics.views.get_realtime_data",
                    return_value={
                        "active": {"count": 0, "visitors": []},
                        "recent_events": [], "current_pages": [],
                    },
                ),
            ):
                response = client.get(ROUTES[page])
            assert response.status_code == 200
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# Service orchestration — Retention
# ---------------------------------------------------------------------------


class TestRetentionServiceOrchestration:
    @patch("apps.analytics.services.get_retention")
    def test_calls_get_retention(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_retention_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {"cohort": "2025-01-06", "cohortSize": 100, "periods": [100.0, 50.0, 25.0]},
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 3, 1, tzinfo=UTC),
        )
        result = get_retention_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert mock_fn.call_args[0][0] == WEBSITE_ID
        assert "cohorts" in result
        assert result["granularity"] == "week"

    @patch("apps.analytics.services.get_retention")
    def test_monthly_granularity(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_retention_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = []
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 6, 1, tzinfo=UTC),
        )
        result = get_retention_data(WEBSITE_ID, date_range, granularity="month")
        assert mock_fn.call_args[1]["granularity"] == "month" or mock_fn.call_args[0][3] == "month"
        assert result["granularity"] == "month"

    @patch("apps.analytics.services.get_retention")
    def test_invalid_granularity_defaults_to_week(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_retention_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = []
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 3, 1, tzinfo=UTC),
        )
        result = get_retention_data(WEBSITE_ID, date_range, granularity="invalid")
        assert result["granularity"] == "week"


# ---------------------------------------------------------------------------
# Service orchestration — Funnels
# ---------------------------------------------------------------------------


class TestFunnelsServiceOrchestration:
    @patch("apps.analytics.services.get_funnel")
    def test_calls_get_funnel_with_default_steps(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_funnels_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {"step": 1, "label": "/", "visitors": 100, "dropoff": 0, "conversionRate": 100.0},
            {"step": 2, "label": "/pricing", "visitors": 50, "dropoff": 50, "conversionRate": 50.0},
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_funnels_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert "funnel_steps" in result
        assert "steps_config" in result
        assert len(result["steps_config"]) == 3  # default steps

    @patch("apps.analytics.services.get_funnel")
    def test_custom_steps(self, mock_fn: MagicMock) -> None:
        from apps.analytics.services import get_funnels_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = []
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        custom_steps = [{"type": "url", "value": "/home"}, {"type": "url", "value": "/about"}]
        result = get_funnels_data(WEBSITE_ID, date_range, steps=custom_steps)
        assert result["steps_config"] == custom_steps


# ---------------------------------------------------------------------------
# Service orchestration — Journeys
# ---------------------------------------------------------------------------


class TestJourneysServiceOrchestration:
    @patch("apps.analytics.services.get_section_conversions", return_value=[])
    @patch("apps.analytics.services.get_section_journeys")
    def test_calls_get_journeys(
        self, mock_fn: MagicMock, mock_conv: MagicMock,
    ) -> None:
        from apps.analytics.services import get_journeys_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {"path": ["/", "/about", "/contact"], "count": 42, "percentage": 35.0},
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_journeys_data(WEBSITE_ID, date_range)
        assert mock_fn.call_count == 1
        assert "journeys" in result
        assert "sankey" in result

    @patch("apps.analytics.services.get_section_conversions", return_value=[])
    @patch("apps.analytics.services.get_section_journeys")
    def test_sankey_data_structure(
        self, mock_fn: MagicMock, mock_conv: MagicMock,
    ) -> None:
        from apps.analytics.services import get_journeys_data
        from core.mantecato_core.date_utils import DateRange

        mock_fn.return_value = [
            {"path": ["/", "/about"], "count": 10, "percentage": 50.0},
            {"path": ["/", "/pricing"], "count": 8, "percentage": 40.0},
        ]
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_journeys_data(WEBSITE_ID, date_range)
        sankey = result["sankey"]
        assert "nodes" in sankey
        assert "links" in sankey
        node_names = [n["name"] for n in sankey["nodes"]]
        assert "/" in node_names
        assert "/about" in node_names


# ---------------------------------------------------------------------------
# Service orchestration — Revenue
# ---------------------------------------------------------------------------


class TestRevenueServiceOrchestration:
    @patch("apps.analytics.services.get_revenue_by_country", return_value=[])
    @patch("apps.analytics.services.get_revenue_by_event", return_value=[])
    @patch("apps.analytics.services.get_revenue_time_series", return_value=[])
    @patch("apps.analytics.services.get_revenue_summary")
    def test_calls_four_query_functions(
        self,
        mock_summary: MagicMock,
        mock_ts: MagicMock,
        mock_event: MagicMock,
        mock_country: MagicMock,
    ) -> None:
        from apps.analytics.services import get_revenue_data
        from core.mantecato_core.date_utils import DateRange

        mock_summary.return_value = {
            "totalRevenue": 1000, "transactions": 50,
            "uniqueCustomers": 30, "arpu": 33.33,
        }
        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_revenue_data(WEBSITE_ID, date_range)
        assert mock_summary.call_count == 1
        assert mock_ts.call_count == 1
        assert mock_event.call_count == 1
        assert mock_country.call_count == 1
        assert "summary" in result
        assert result["summary"]["totalRevenue"] == 1000
        assert "revenue_chart_data" in result


# ---------------------------------------------------------------------------
# Service orchestration — Engagement
# ---------------------------------------------------------------------------


class TestEngagementServiceOrchestration:
    @patch("apps.analytics.services.get_bounce_rate_by_source", return_value=[])
    @patch("apps.analytics.services.get_bounce_rate_by_page", return_value=[])
    @patch("apps.analytics.services.get_duration_by_page", return_value=[])
    @patch("apps.analytics.services.get_duration_percentiles", return_value={})
    @patch("apps.analytics.services.get_duration_distribution", return_value=[])
    def test_calls_five_query_functions(
        self,
        mock_dist: MagicMock,
        mock_pct: MagicMock,
        mock_dur: MagicMock,
        mock_brp: MagicMock,
        mock_brs: MagicMock,
    ) -> None:
        from apps.analytics.services import get_engagement_data
        from core.mantecato_core.date_utils import DateRange

        date_range = DateRange(
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 1, 31, tzinfo=UTC),
        )
        result = get_engagement_data(WEBSITE_ID, date_range)
        assert mock_dist.call_count == 1
        assert mock_pct.call_count == 1
        assert mock_dur.call_count == 1
        assert mock_brp.call_count == 1
        assert mock_brs.call_count == 1
        assert "distribution" in result
        assert "percentiles" in result
        assert "distribution_chart_data" in result
        assert "bounce_chart_data" in result


# ---------------------------------------------------------------------------
# Service orchestration — Realtime
# ---------------------------------------------------------------------------


class TestRealtimeServiceOrchestration:
    @patch("apps.analytics.services.get_current_pages", return_value=[])
    @patch("apps.analytics.services.get_recent_events", return_value=[])
    @patch("apps.analytics.services.get_active_visitors")
    def test_calls_three_query_functions(
        self,
        mock_active: MagicMock,
        mock_events: MagicMock,
        mock_pages: MagicMock,
    ) -> None:
        from apps.analytics.services import get_realtime_data

        mock_active.return_value = {"count": 5, "visitors": []}
        result = get_realtime_data(WEBSITE_ID)
        assert mock_active.call_count == 1
        assert mock_events.call_count == 1
        assert mock_pages.call_count == 1
        assert "active" in result
        assert result["active"]["count"] == 5


# ---------------------------------------------------------------------------
# Template existence and structure
# ---------------------------------------------------------------------------


class TestAdvancedTemplateFiles:
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

    def test_realtime_partial_exists(self) -> None:
        assert (ANALYTICS_DIR / "_realtime_data.html").is_file()


# ---------------------------------------------------------------------------
# Template content specifics
# ---------------------------------------------------------------------------


class TestAdvancedTemplateContent:
    def test_retention_has_cohort_table(self) -> None:
        content = (ANALYTICS_DIR / "retention.html").read_text()
        assert "<table" in content
        assert "Cohort" in content

    def test_funnels_has_chart_canvas(self) -> None:
        content = (ANALYTICS_DIR / "funnels.html").read_text()
        assert "canvas" in content
        assert "json_script" in content
        assert "initBarChart" in content

    def test_funnels_has_step_table(self) -> None:
        content = (ANALYTICS_DIR / "funnels.html").read_text()
        assert "Step" in content
        assert "Conversion" in content

    def test_journeys_has_sankey_container(self) -> None:
        content = (ANALYTICS_DIR / "journeys.html").read_text()
        assert "sankey" in content.lower()
        assert "d3-sankey" in content or "d3" in content

    def test_journeys_has_journey_table(self) -> None:
        content = (ANALYTICS_DIR / "journeys.html").read_text()
        assert "<table" in content
        assert "Path" in content

    def test_revenue_has_summary_cards(self) -> None:
        content = (ANALYTICS_DIR / "revenue.html").read_text()
        assert "Total Revenue" in content
        assert "Transactions" in content

    def test_revenue_has_charts(self) -> None:
        content = (ANALYTICS_DIR / "revenue.html").read_text()
        assert "canvas" in content
        assert "initTimeSeriesChart" in content

    def test_engagement_has_percentile_cards(self) -> None:
        content = (ANALYTICS_DIR / "engagement.html").read_text()
        assert "Median" in content
        assert "P90" in content

    def test_engagement_has_distribution_chart(self) -> None:
        content = (ANALYTICS_DIR / "engagement.html").read_text()
        assert "canvas" in content
        assert "initBarChart" in content

    def test_realtime_uses_htmx_polling(self) -> None:
        content = (ANALYTICS_DIR / "realtime.html").read_text()
        assert "hx-trigger" in content
        assert "every" in content
        assert "5s" in content

    def test_realtime_has_active_indicator(self) -> None:
        content = (ANALYTICS_DIR / "_realtime_data.html").read_text()
        assert "Active Visitors" in content or "active" in content.lower()

    def test_realtime_partial_includes_event_stream(self) -> None:
        content = (ANALYTICS_DIR / "_realtime_data.html").read_text()
        has_stream = (
            "Live Event Stream" in content
            or "recent_events" in content
            or "event" in content.lower()
        )
        assert has_stream


# ---------------------------------------------------------------------------
# No forbidden JS frameworks in new templates
# ---------------------------------------------------------------------------


class TestAdvancedTemplatesForbidden:
    FORBIDDEN = ["react", "vue", "alpine", "jquery"]

    @pytest.mark.parametrize("page", PAGES)
    def test_no_forbidden_frameworks(self, page: str) -> None:
        content = (ANALYTICS_DIR / f"{page}.html").read_text().lower()
        for fw in self.FORBIDDEN:
            assert fw not in content, f"{page}.html must not contain {fw}"

    def test_realtime_partial_no_forbidden_frameworks(self) -> None:
        content = (ANALYTICS_DIR / "_realtime_data.html").read_text().lower()
        for fw in self.FORBIDDEN:
            assert fw not in content, f"_realtime_data.html must not contain {fw}"


# ---------------------------------------------------------------------------
# Base template nav has real URLs for Phase 4 pages
# ---------------------------------------------------------------------------


class TestBaseNavAdvancedUrls:
    @pytest.fixture(autouse=True)
    def _read_base(self) -> None:
        self.content = BASE_HTML.read_text()

    def test_retention_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_retention' %}" in self.content

    def test_funnels_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_funnels' %}" in self.content

    def test_journeys_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_journeys' %}" in self.content

    def test_revenue_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_revenue' %}" in self.content

    def test_engagement_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_engagement' %}" in self.content

    def test_realtime_link_uses_url_tag(self) -> None:
        assert "{% url 'analytics_realtime' %}" in self.content

    def test_no_hash_hrefs_for_advanced_pages(self) -> None:
        """Retention, Funnels, Journeys, Revenue must not use href="#"."""
        for label in ["Retention", "Funnels", "Journeys", "Revenue", "Engagement", "Realtime"]:
            lines = self.content.split("\n")
            for line in lines:
                if label in line and "nav-link" in line:
                    assert 'href="#"' not in line, f"Nav link for {label} still uses href=#"


# ---------------------------------------------------------------------------
# No write SQL in analytics app (re-check with new code)
# ---------------------------------------------------------------------------


class TestAnalyticsNoWriteSqlAdvanced:
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
# View rendering with mocked services
# ---------------------------------------------------------------------------


class TestAdvancedViewRendered:
    def _setup_client(self, client: Client) -> None:
        _login_as_admin(client)
        self._patcher = _patch_middleware_user(client)

    def teardown_method(self) -> None:
        if hasattr(self, "_patcher"):
            self._patcher.stop()

    @patch("apps.analytics.views.get_retention_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_retention_renders_cohort_data(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "cohorts": [
                {"cohort": "2025-01-06T00:00:00", "cohortSize": 100,
                 "periods": [100.0, 50.0, 25.0]},
            ],
            "granularity": "week",
        }
        response = client.get("/retention/")
        content = response.content.decode()
        assert "100" in content
        assert "50%" in content

    @patch("apps.analytics.views.get_funnels_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_funnels_renders_steps(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "funnel_steps": [
                {"step": 1, "label": "/", "visitors": 100,
                 "dropoff": 0, "conversionRate": 100.0},
                {"step": 2, "label": "/pricing", "visitors": 50,
                 "dropoff": 50, "conversionRate": 50.0},
            ],
            "steps_config": [
                {"type": "url", "value": "/"},
                {"type": "url", "value": "/pricing"},
            ],
            "funnel_chart_data": {"labels": ["/", "/pricing"], "datasets": [{"data": [100, 50]}]},
        }
        response = client.get("/funnels/")
        content = response.content.decode()
        assert "pricing" in content
        assert "100" in content

    @patch("apps.analytics.views.get_entry_exit_data")
    @patch("apps.analytics.views.get_journeys_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_journeys_renders_paths(
        self, mock_websites: MagicMock, mock_data: MagicMock,
        mock_entry_exit: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "journeys": [
                {"path": ["/", "/about"], "count": 42, "percentage": 35.0},
            ],
            "sankey": {
                "nodes": [{"name": "/"}, {"name": "/about"}],
                "links": [{"source": 0, "target": 1, "value": 42}],
            },
            "mode": "sections",
            "conversions": [],
        }
        mock_entry_exit.return_value = {"entry_pages": [], "exit_pages": []}
        response = client.get("/journeys/")
        content = response.content.decode()
        assert "about" in content
        assert "42" in content

    @patch("apps.analytics.views.get_revenue_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_revenue_renders_summary(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "summary": {
                "totalRevenue": 1234.56, "transactions": 42,
                "uniqueCustomers": 30, "arpu": 41.15,
            },
            "time_series": [],
            "by_event": [],
            "by_country": [],
            "revenue_chart_data": {"labels": [], "datasets": []},
            "event_chart_data": {"labels": [], "datasets": []},
        }
        response = client.get("/revenue/")
        content = response.content.decode()
        assert "1234" in content
        assert "42" in content

    @patch("apps.analytics.views.get_heatmap_data")
    @patch("apps.analytics.views.get_engagement_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_engagement_renders_percentiles(
        self, mock_websites: MagicMock, mock_data: MagicMock,
        mock_heatmap: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "distribution": [],
            "percentiles": {
                "median": 45, "p75": 90, "p90": 150,
                "p95": 200, "p99": 300, "avg": 60, "totalVisits": 500,
            },
            "duration_by_page": [],
            "bounce_by_page": [],
            "bounce_by_source": [],
            "distribution_chart_data": {"labels": [], "datasets": []},
            "bounce_chart_data": {"labels": [], "datasets": []},
        }
        mock_heatmap.return_value = {
            "grid": [[0] * 24 for _ in range(7)],
            "max_val": 0,
        }
        response = client.get("/engagement/")
        content = response.content.decode()
        assert "45" in content
        assert "500" in content

    @patch("apps.analytics.views.get_realtime_data")
    @patch("apps.analytics.views.resolve_websites_for_user")
    def test_realtime_renders_active_visitors(
        self, mock_websites: MagicMock, mock_data: MagicMock, client: Client,
    ) -> None:
        self._setup_client(client)
        mock_websites.return_value = [
            {"id": WEBSITE_ID, "name": "Test Site", "domain": "test.com"},
        ]
        mock_data.return_value = {
            "active": {"count": 7, "visitors": [
                {
                    "sessionId": "s1", "urlPath": "/",
                    "country": "US", "city": "NYC",
                    "browser": "Chrome", "os": "Mac",
                },
            ]},
            "recent_events": [
                {
                    "createdAt": "2025-01-15T10:30:00", "urlPath": "/",
                    "eventType": 1, "eventName": None,
                    "country": "US", "browser": "Chrome",
                },
            ],
            "current_pages": [
                {"urlPath": "/", "visitors": 5},
            ],
        }
        response = client.get("/realtime/")
        content = response.content.decode()
        assert "hx-trigger" in content
        assert "every 5s" in content

    @patch("apps.analytics.partials.get_realtime_data")
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
