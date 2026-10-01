"""Small contracts keeping polling and production tracing lightweight."""

from pathlib import Path
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.analytics.services import get_realtime_data
from core.mantecato_core.database import get_query_log, reset_query_log
from mantecato.middleware import QueryTimingMiddleware


def test_realtime_only_fetches_the_three_visible_datasets():
    with (
        patch("apps.analytics.services.get_overview_data") as overview,
        patch("apps.analytics.services.get_active_pageviews", return_value={"count": 1}) as active,
        patch("apps.analytics.services.get_recent_pageviews", return_value=[]) as recent,
        patch("apps.analytics.services.get_current_pages", return_value=[]) as pages,
    ):
        filters = [object()]
        data = get_realtime_data("site", filters)
    assert set(data) == {"realtime", "recent_events", "current_pages"}
    overview.assert_not_called()
    for method in (active, recent, pages):
        method.assert_called_once_with("site", filters=filters)


@override_settings(DEBUG=False, QUERY_SUMMARY_LOG=False)
def test_production_does_not_capture_query_summaries_by_default():
    with patch("core.mantecato_core.database.reset_query_log") as reset:
        response = QueryTimingMiddleware(lambda req: HttpResponse())(RequestFactory().get("/"))
    reset.assert_called_once_with(enabled=False)
    assert "Server-Timing" not in response


@override_settings(DEBUG=True, QUERY_SUMMARY_LOG=False)
def test_debug_still_has_server_timing():
    response = QueryTimingMiddleware(lambda req: HttpResponse())(RequestFactory().get("/"))
    assert "Server-Timing" in response
    reset_query_log(enabled=False)
    assert get_query_log() == []


def test_realtime_poller_is_visibility_filtered_and_drops_overlaps():
    html = (Path(__file__).resolve().parents[1] / "templates/analytics/realtime.html").read_text()
    assert "every 5s [!document.hidden]" in html
    assert 'hx-sync="this:drop"' in html


def test_lazy_panels_keep_filters_and_load_on_selection_only():
    root = Path(__file__).resolve().parents[1] / "templates"
    panels = (root / "analytics/_overview_tables.html").read_text()
    assert panels.count('hx-trigger="panelshown"') == 2
    assert panels.count('hx-sync="closest main:queue all"') == 2
    assert "{% view_query %}&amp;tab=pages" in panels
    assert "{% view_query %}&amp;tab=sources" in panels
    base = (root / "base.html").read_text()
    assert 'target.dataset.loaded !== "true"' in base
    assert "event.detail.successful" in base
