"""Tests for base template structure and content requirements.

Verifies that base.html contains all required CDN includes, Django blocks,
i18n support, and excludes forbidden JS frameworks. No database access needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
BASE_HTML = TEMPLATES_DIR / "base.html"
STATIC_JS = Path(__file__).resolve().parent.parent / "static" / "js"
CHARTS_JS = STATIC_JS / "charts.js"
COMPONENTS_DIR = TEMPLATES_DIR / "components"


class TestBaseTemplateExists:
    def test_base_html_file_exists(self):
        assert BASE_HTML.is_file(), "templates/base.html must exist"

    def test_components_directory_exists(self):
        assert COMPONENTS_DIR.is_dir(), "templates/components/ directory must exist"

    def test_charts_js_file_exists(self):
        assert CHARTS_JS.is_file(), "static/js/charts.js must exist"


class TestBaseHtmlRequiredIncludes:
    @pytest.fixture(autouse=True)
    def _read_template(self):
        self.content = BASE_HTML.read_text()

    def test_contains_htmx(self):
        assert "htmx.org" in self.content, "Must include HTMX via CDN"

    def test_contains_tailwind(self):
        assert "tailwindcss" in self.content, "Must include Tailwind CSS via CDN"

    def test_contains_chart_js(self):
        assert "chart.js" in self.content, "Must include Chart.js via CDN"

    def test_loads_i18n_and_static(self):
        # The first line is a single {% load %} with at least i18n + static
        # (other libraries such as fmt may be appended).
        load_line = self.content.splitlines()[0]
        assert load_line.startswith("{% load ") and load_line.endswith("%}"), (
            "First line must be a {% load %} tag"
        )
        assert "i18n" in load_line and "static" in load_line, (
            "Must load i18n and static template tags"
        )

    def test_contains_trans_tags(self):
        assert "{% trans" in self.content, "Must use {% trans %} for i18n"


class TestBaseHtmlForbiddenContent:
    @pytest.fixture(autouse=True)
    def _read_template(self):
        self.content = BASE_HTML.read_text().lower()

    def test_no_react(self):
        assert "react" not in self.content, "Must not include React"

    def test_no_vue(self):
        assert "vue" not in self.content, "Must not include Vue"

    def test_no_alpine(self):
        assert "alpine" not in self.content, "Must not include Alpine"

    def test_no_jquery(self):
        assert "jquery" not in self.content, "Must not include jQuery"

    def test_no_vite(self):
        assert "vite" not in self.content, "Must not reference Vite"


class TestBaseHtmlDjangoBlocks:
    @pytest.fixture(autouse=True)
    def _read_template(self):
        self.content = BASE_HTML.read_text()

    def test_has_content_block(self):
        assert "{% block content %}" in self.content, "Must define content block"

    def test_has_extra_scripts_block(self):
        assert "{% block extra_scripts %}" in self.content, (
            "Must define extra_scripts block"
        )

    def test_has_title_block(self):
        assert "{% block title %}" in self.content, "Must define title block"

    def test_has_extra_head_block(self):
        assert "{% block extra_head %}" in self.content, "Must define extra_head block"

    def test_has_page_title_block(self):
        assert "{% block page_title %}" in self.content, (
            "Must define page_title block for topbar"
        )


class TestBaseHtmlNavigation:
    @pytest.fixture(autouse=True)
    def _read_template(self):
        self.content = BASE_HTML.read_text()

    def test_has_sidebar(self):
        assert "sidebar" in self.content.lower(), "Must have sidebar navigation"

    def test_has_topbar(self):
        assert "header" in self.content.lower(), "Must have topbar/header"

    def test_has_overview_link(self):
        assert "Overview" in self.content or "overview" in self.content.lower(), (
            "Must have Overview nav link"
        )

    def test_has_pages_link(self):
        assert "Pages" in self.content, "Must have Pages nav link"

    def test_has_events_link(self):
        assert "Events" in self.content, "Must have Events nav link"

    def test_has_devices_link(self):
        assert "Devices" in self.content, "Must have Devices nav link"

    def test_has_geo_link(self):
        assert "Geo" in self.content, "Must have Geo nav link"

    def test_has_realtime_link(self):
        assert "Realtime" in self.content, "Must have Realtime nav link"

    def test_has_settings_link(self):
        assert "Settings" in self.content, "Must have Settings nav link"


class TestBaseHtmlResponsiveAndCsrf:
    @pytest.fixture(autouse=True)
    def _read_template(self):
        self.content = BASE_HTML.read_text()

    def test_has_viewport_meta(self):
        assert "viewport" in self.content, "Must have viewport meta tag"

    def test_has_csrf_token(self):
        assert "csrf_token" in self.content, "Must include CSRF token support"

    def test_has_mobile_sidebar_toggle(self):
        assert "sidebar-toggle" in self.content, (
            "Must have mobile sidebar toggle button"
        )

    def test_messages_block(self):
        assert "messages" in self.content, "Must support Django messages framework"


class TestChartsJsPlaceholder:
    def test_charts_js_is_vanilla_js(self):
        content = CHARTS_JS.read_text().lower()
        assert "react" not in content
        assert "vue" not in content
        assert "jquery" not in content

    def test_charts_js_has_init_functions(self):
        content = CHARTS_JS.read_text()
        assert "initTimeSeriesChart" in content
        assert "initBarChart" in content
        assert "initPieChart" in content
        assert "initSparkline" in content

    def test_charts_js_has_reinit_listener(self):
        content = CHARTS_JS.read_text()
        assert "_reinitAllCharts" in content


class TestStatCardComponent:
    def test_stat_card_exists(self):
        assert (COMPONENTS_DIR / "stat_card.html").is_file(), (
            "templates/components/stat_card.html must exist"
        )

    def test_stat_card_uses_i18n(self):
        content = (COMPONENTS_DIR / "stat_card.html").read_text()
        assert "{% load i18n %}" in content or "{% trans" in content, (
            "stat_card.html should load i18n or use trans tags"
        )


class TestViewQueryTag:
    """The ``view_query`` tag preserves analytics view-state across links."""

    @staticmethod
    def _render(params, context_extra=None):
        from django.template import Context, Template
        from django.test import RequestFactory

        request = RequestFactory().get("/", data=params)
        ctx = {"request": request}
        if context_extra:
            ctx.update(context_extra)
        return Template("{% load fmt %}{% view_query %}").render(Context(ctx))

    def test_preserves_range_filter_and_bot_filter(self):
        out = self._render(
            {"website": "W1", "range": "7d", "filter": "country:eq:IT", "bot_filter": "1"}
        )
        assert "website=W1" in out
        assert "range=7d" in out
        assert "filter=country%3Aeq%3AIT" in out
        assert "bot_filter=1" in out

    def test_preserves_multiple_filters(self):
        from urllib.parse import parse_qs

        out = self._render(
            {"website": "W1", "filter": ["country:eq:IT", "browser:eq:Chrome"]}
        )
        # The tag output is HTML-autoescaped (``&`` -> ``&amp;``), which is the
        # correct encoding inside an href attribute; unescape before parsing.
        assert parse_qs(out.replace("&amp;", "&"))["filter"] == [
            "country:eq:IT",
            "browser:eq:Chrome",
        ]

    def test_falls_back_to_selected_website(self):
        # No ?website= in the URL -> the resolved website from context is used.
        out = self._render({"range": "30d"}, context_extra={"selected_website": "W9"})
        assert "website=W9" in out
        assert "range=30d" in out

    def test_skips_unrelated_and_empty_params(self):
        out = self._render({"website": "W1", "foo": "bar", "range": ""})
        assert "foo" not in out
        assert "range=" not in out
