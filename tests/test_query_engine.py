"""Smoke tests for the analytics query engine.

Seeds a small dataset via the ORM, then calls every read-only query function
and asserts it executes and returns the documented shape. This gives the
raw-SQL query modules real, isolated coverage on the transactional test
database — previously they were exercised only by skipped live-DB tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.core.models import EventData, Revenue, Session, Website, WebsiteEvent
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries import (
    get_active_visitors,
    get_bounce_rate_by_page,
    get_bounce_rate_by_source,
    get_channel_metrics,
    get_click_id_metrics,
    get_comparison_stats,
    get_country_breakdown,
    get_current_pages,
    get_device_metrics,
    get_duration_by_page,
    get_duration_distribution,
    get_duration_percentiles,
    get_event_metrics,
    get_event_properties,
    get_event_time_series,
    get_filter_values,
    get_first_event_date,
    get_funnel,
    get_geo_metrics,
    get_hostname_metrics,
    get_journeys,
    get_next_pages,
    get_page_metrics,
    get_page_referrers,
    get_page_time_series,
    get_pageview_time_series,
    get_recent_events,
    get_referrer_metrics,
    get_referrer_pages,
    get_retention,
    get_revenue_by_country,
    get_revenue_by_event,
    get_revenue_summary,
    get_revenue_time_series,
    get_session_activity,
    get_session_list,
    get_sessions_for_bucket,
    get_time_on_page_distribution,
    get_top_events,
    get_top_events_with_properties,
    get_top_pages,
    get_top_referrers,
    get_top_sections,
    get_traffic_heatmap,
    get_utm_detail_metrics,
    get_utm_metrics,
    get_website_stats,
)

pytestmark = pytest.mark.django_db


def _seed() -> dict:
    """Create one website with sessions, pageviews, events, data, and revenue."""
    website = Website.objects.create(name="Test Site", domain="example.com", is_deleted=False)
    sessions = []
    for browser, os_name, device, country in [
        ("Chrome", "macOS", "desktop", "US"),
        ("Firefox", "Windows", "desktop", "GB"),
        ("Safari", "iOS", "mobile", "DE"),
    ]:
        sessions.append(
            Session.objects.create(
                website_id=website.id,
                browser=browser,
                os=os_name,
                device=device,
                country=country,
                region="Region",
                city="City",
                language="en",
                screen="1920x1080",
            )
        )

    for i, session in enumerate(sessions):
        visit = uuid.uuid4()
        for path in ("/", "/about", "/pricing", "/blog/post-1"):
            WebsiteEvent.objects.create(
                website_id=website.id,
                session_id=session.session_id,
                visit_id=visit,
                url_path=path,
                event_type=1,
                page_title=f"Page {path}",
                referrer_domain="google.com" if i == 0 else "twitter.com",
                hostname="example.com",
                browser=session.browser,
                os=session.os,
                device=session.device,
                country=session.country,
                region=session.region,
                city=session.city,
                language="en",
                utm_source="google",
                utm_medium="cpc",
                utm_campaign="spring",
                gclid="gclid-123",
            )

    for session in sessions[:2]:
        event = WebsiteEvent.objects.create(
            website_id=website.id,
            session_id=session.session_id,
            visit_id=uuid.uuid4(),
            url_path="/checkout",
            event_type=2,
            event_name="purchase",
            hostname="example.com",
        )
        EventData.objects.create(
            website_id=website.id,
            website_event_id=event.event_id,
            data_key="plan",
            string_value="pro",
            data_type=1,
        )
        Revenue.objects.create(
            website_id=website.id,
            session_id=session.session_id,
            event_id=event.event_id,
            event_name="purchase",
            revenue=Decimal("49.99"),
            currency="USD",
        )

    return {
        "website_id": str(website.id),
        "session_id": str(sessions[0].session_id),
    }


class _SeededQueries:
    """Base class: seeds data and exposes ids plus a covering date range."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        data = _seed()
        self.website_id = data["website_id"]
        self.session_id = data["session_id"]
        now = datetime.now(UTC)
        self.start = now - timedelta(days=1)
        self.end = now + timedelta(days=1)


class TestStatsQueries(_SeededQueries):
    def test_first_event_date(self) -> None:
        result = get_first_event_date(self.website_id)
        assert result is None or isinstance(result, datetime)

    def test_website_stats(self) -> None:
        result = get_website_stats(self.website_id, self.start, self.end)
        assert result["pageviews"] == 12
        assert result["visitors"] == 3

    def test_pageview_time_series(self) -> None:
        assert isinstance(
            get_pageview_time_series(self.website_id, self.start, self.end, "day"), list
        )

    def test_top_pages(self) -> None:
        result = get_top_pages(self.website_id, self.start, self.end)
        assert isinstance(result, list)
        assert any(p["urlPath"] == "/" for p in result)

    def test_top_sections(self) -> None:
        assert isinstance(get_top_sections(self.website_id, self.start, self.end), list)

    def test_top_referrers(self) -> None:
        assert isinstance(get_top_referrers(self.website_id, self.start, self.end), list)

    def test_top_events(self) -> None:
        result = get_top_events(self.website_id, self.start, self.end)
        assert any(e["eventName"] == "purchase" for e in result)

    def test_top_events_with_properties(self) -> None:
        assert isinstance(
            get_top_events_with_properties(self.website_id, self.start, self.end), list
        )

    def test_country_breakdown(self) -> None:
        assert isinstance(get_country_breakdown(self.website_id, self.start, self.end), list)


class TestDimensionQueries(_SeededQueries):
    def test_device_metrics(self) -> None:
        assert isinstance(
            get_device_metrics(self.website_id, self.start, self.end, "browser"), list
        )

    def test_geo_metrics(self) -> None:
        assert isinstance(get_geo_metrics(self.website_id, self.start, self.end), list)

    def test_traffic_heatmap(self) -> None:
        assert isinstance(get_traffic_heatmap(self.website_id, self.start, self.end), list)


class TestEventQueries(_SeededQueries):
    def test_event_metrics(self) -> None:
        assert isinstance(get_event_metrics(self.website_id, self.start, self.end), list)

    def test_event_time_series(self) -> None:
        assert isinstance(
            get_event_time_series(self.website_id, "purchase", self.start, self.end, "day"),
            list,
        )

    def test_event_properties(self) -> None:
        assert isinstance(
            get_event_properties(self.website_id, "purchase", self.start, self.end), list
        )


class TestSessionQueries(_SeededQueries):
    def test_session_list(self) -> None:
        assert isinstance(get_session_list(self.website_id, self.start, self.end), list)

    def test_session_activity(self) -> None:
        assert isinstance(get_session_activity(self.session_id, self.website_id), list)


class TestPageviewQueries(_SeededQueries):
    def test_page_metrics(self) -> None:
        assert isinstance(get_page_metrics(self.website_id, self.start, self.end), list)

    def test_page_referrers(self) -> None:
        assert isinstance(get_page_referrers(self.website_id, "/", self.start, self.end), list)

    def test_next_pages(self) -> None:
        assert isinstance(get_next_pages(self.website_id, "/", self.start, self.end), list)

    def test_time_on_page_distribution(self) -> None:
        assert isinstance(
            get_time_on_page_distribution(self.website_id, "/", self.start, self.end), list
        )

    def test_page_time_series(self) -> None:
        assert isinstance(
            get_page_time_series(self.website_id, "/", self.start, self.end, "day"), list
        )


class TestSourceQueries(_SeededQueries):
    def test_referrer_metrics(self) -> None:
        assert isinstance(get_referrer_metrics(self.website_id, self.start, self.end), list)

    def test_utm_metrics(self) -> None:
        assert isinstance(get_utm_metrics(self.website_id, self.start, self.end), list)

    def test_utm_detail_metrics(self) -> None:
        assert isinstance(
            get_utm_detail_metrics(self.website_id, self.start, self.end, "utm_source"), list
        )

    def test_channel_metrics(self) -> None:
        assert isinstance(get_channel_metrics(self.website_id, self.start, self.end), list)

    def test_click_id_metrics(self) -> None:
        assert isinstance(get_click_id_metrics(self.website_id, self.start, self.end), list)

    def test_referrer_pages(self) -> None:
        assert isinstance(
            get_referrer_pages(self.website_id, self.start, self.end, "google.com"), list
        )

    def test_hostname_metrics(self) -> None:
        assert isinstance(get_hostname_metrics(self.website_id, self.start, self.end), list)


class TestEngagementQueries(_SeededQueries):
    def test_duration_distribution(self) -> None:
        assert isinstance(get_duration_distribution(self.website_id, self.start, self.end), list)

    def test_duration_percentiles(self) -> None:
        assert isinstance(get_duration_percentiles(self.website_id, self.start, self.end), dict)

    def test_duration_by_page(self) -> None:
        assert isinstance(get_duration_by_page(self.website_id, self.start, self.end), list)

    def test_bounce_rate_by_page(self) -> None:
        assert isinstance(get_bounce_rate_by_page(self.website_id, self.start, self.end), list)

    def test_bounce_rate_by_source(self) -> None:
        assert isinstance(get_bounce_rate_by_source(self.website_id, self.start, self.end), list)

    def test_sessions_for_bucket(self) -> None:
        assert isinstance(
            get_sessions_for_bucket(self.website_id, self.start, self.end, "1-10s"), dict
        )


class TestOtherQueries(_SeededQueries):
    def test_funnel(self) -> None:
        steps = [{"type": "url", "value": "/"}, {"type": "url", "value": "/about"}]
        assert isinstance(get_funnel(self.website_id, self.start, self.end, steps), list)

    def test_retention(self) -> None:
        assert isinstance(get_retention(self.website_id, self.start, self.end), list)

    def test_journeys(self) -> None:
        assert isinstance(get_journeys(self.website_id, self.start, self.end), list)

    def test_active_visitors(self) -> None:
        assert isinstance(get_active_visitors(self.website_id), dict)

    def test_recent_events(self) -> None:
        assert isinstance(get_recent_events(self.website_id), list)

    def test_current_pages(self) -> None:
        assert isinstance(get_current_pages(self.website_id), list)

    def test_comparison_stats(self) -> None:
        prev_start = self.start - timedelta(days=2)
        prev_end = self.start - timedelta(days=1)
        assert isinstance(
            get_comparison_stats(self.website_id, self.start, self.end, prev_start, prev_end),
            list,
        )

    def test_revenue_summary(self) -> None:
        assert isinstance(get_revenue_summary(self.website_id, self.start, self.end), dict)

    def test_revenue_time_series(self) -> None:
        assert isinstance(
            get_revenue_time_series(self.website_id, self.start, self.end, "day"), list
        )

    def test_revenue_by_event(self) -> None:
        assert isinstance(get_revenue_by_event(self.website_id, self.start, self.end), list)

    def test_revenue_by_country(self) -> None:
        assert isinstance(get_revenue_by_country(self.website_id, self.start, self.end), list)

    def test_filter_values(self) -> None:
        assert isinstance(
            get_filter_values(self.website_id, "url_path", self.start, self.end), list
        )


class TestQueriesWithFilters(_SeededQueries):
    """Exercise the filter path: a session-column filter forces the JOIN."""

    def test_session_column_filter(self) -> None:
        filters = [Filter(column="browser", operator="eq", value="Chrome")]
        stats = get_website_stats(self.website_id, self.start, self.end, filters)
        assert stats["visitors"] == 1
        assert isinstance(
            get_top_pages(self.website_id, self.start, self.end, filters=filters), list
        )
        assert isinstance(
            get_referrer_metrics(self.website_id, self.start, self.end, filters=filters), list
        )

    def test_event_column_filter(self) -> None:
        filters = [Filter(column="url_path", operator="contains", value="about")]
        result = get_top_pages(self.website_id, self.start, self.end, filters=filters)
        assert all("about" in p["urlPath"] for p in result)
        assert isinstance(
            get_pageview_time_series(self.website_id, self.start, self.end, "day", filters), list
        )
