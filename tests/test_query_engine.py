"""Smoke tests for the analytics query engine — privacy-first aggregate mode.

Seeds a small dataset via the ORM, then calls every active read-only query
function and asserts it executes and returns the documented shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from apps.core.models import Website, WebsiteEvent
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries import (
    get_comparison_stats,
    get_country_breakdown,
    get_current_pages,
    get_device_metrics,
    get_device_metrics_multi,
    get_filter_values,
    get_first_event_date,
    get_geo_metrics,
    get_page_metrics,
    get_page_time_series,
    get_pageview_time_series,
    get_pageview_time_series_comparison,
    get_recent_pageviews,
    get_top_pages,
    get_top_sections,
    get_traffic_heatmap,
    get_website_stats,
    get_website_stats_comparison,
)

pytestmark = pytest.mark.django_db


def _seed() -> dict:
    """Create one website with anonymous pageview events."""
    website = Website.objects.create(name="Test Site", domain="example.com", is_deleted=False)
    now = datetime.now(UTC)

    for browser, os_name, device, country in [
        ("Chrome", "macOS", "desktop", "US"),
        ("Firefox", "Windows", "desktop", "GB"),
        ("Safari", "iOS", "mobile", "DE"),
    ]:
        for i in range(3):
            WebsiteEvent.objects.create(
                website_id=website.id,
                url_path=f"/page/{i + 1}",
                page_title=f"Page {i + 1}",
                hostname="example.com",
                event_type=1,
                browser=browser,
                os=os_name,
                device=device,
                country=country,
                created_at=now - timedelta(hours=i),
            )

    return {"website": website, "now": now}


class TestWebsiteStats:
    def test_get_website_stats(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_website_stats(wid, start, end)
        assert "pageviews" in result
        assert result["pageviews"] > 0

    def test_get_website_stats_comparison(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        prev_start = start - timedelta(days=7)
        prev_end = start
        result = get_website_stats_comparison(wid, start, end, prev_start, prev_end)
        assert "current" in result
        assert "previous" in result
        assert "pageviews" in result["current"]

    def test_get_first_event_date(self):
        data = _seed()
        result = get_first_event_date(str(data["website"].id))
        assert result is not None


class TestTimeSeries:
    def test_get_pageview_time_series(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_pageview_time_series(wid, start, end, "day")
        assert isinstance(result, list)
        assert all("time" in r and "pageviews" in r for r in result)

    def test_get_pageview_time_series_comparison(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        prev_start = start - timedelta(days=7)
        prev_end = start
        result = get_pageview_time_series_comparison(wid, start, end, prev_start, prev_end, "day")
        assert "current" in result
        assert "previous" in result


class TestTopPages:
    def test_get_top_pages(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_top_pages(wid, start, end, limit=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "urlPath" in result[0]
        assert "views" in result[0]

    def test_get_top_sections(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_top_sections(wid, start, end, limit=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "section" in result[0]
        assert "views" in result[0]


class TestPageMetrics:
    def test_get_page_metrics(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_page_metrics(wid, start, end, limit=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "urlPath" in result[0]
        assert "views" in result[0]
        assert "pageTitle" in result[0]

    def test_get_page_time_series(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_page_time_series(wid, "/page/1", start, end, "day")
        assert isinstance(result, list)
        assert all("time" in r and "views" in r for r in result)


class TestDeviceMetrics:
    def test_get_device_metrics(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        for dim in ("browser", "os", "device"):
            result = get_device_metrics(wid, start, end, dim, limit=10)
            assert isinstance(result, list)
            assert len(result) > 0
            assert "value" in result[0]
            assert "pageviews" in result[0]

    def test_get_device_metrics_multi(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_device_metrics_multi(wid, start, end, limit=10)
        assert "browser" in result
        assert "os" in result
        assert "device" in result


class TestGeoMetrics:
    def test_get_geo_metrics(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_geo_metrics(wid, start, end, limit=10)
        assert isinstance(result, list)

    def test_get_country_breakdown(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_country_breakdown(wid, start, end, limit=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert "country" in result[0]
        assert "pageviews" in result[0]


class TestRealtime:
    def test_get_recent_pageviews(self):
        data = _seed()
        result = get_recent_pageviews(str(data["website"].id))
        assert isinstance(result, list)

    def test_get_current_pages(self):
        data = _seed()
        result = get_current_pages(str(data["website"].id))
        assert isinstance(result, list)


class TestHeatmap:
    def test_get_traffic_heatmap(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_traffic_heatmap(wid, start, end)
        assert isinstance(result, list)
        if result:
            assert "dayOfWeek" in result[0]
            assert "hour" in result[0]
            assert "pageviews" in result[0]


class TestComparison:
    def test_get_comparison_stats(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        prev_start = start - timedelta(days=7)
        prev_end = start
        result = get_comparison_stats(wid, start, end, prev_start, prev_end)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["period"] in ("current", "previous")


class TestFilterValues:
    def test_get_filter_values(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_filter_values(wid, "browser", start, end)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_filter_values_invalid_column(self):
        data = _seed()
        wid = str(data["website"].id)
        start = data["now"] - timedelta(days=7)
        end = data["now"] + timedelta(hours=1)
        result = get_filter_values(wid, "invalid_column", start, end)
        assert result == []
