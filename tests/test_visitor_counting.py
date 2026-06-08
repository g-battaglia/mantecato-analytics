"""Tests for the cookieless **exact** visitor/visit/bounce counter.

Covers the compute-and-discard write path (`record_visit`), the read path
(`read_visit_stats` / `visit_metrics`), the nightly rollup, and the privacy
guarantees (no IP/User-Agent stored, salt discarded at rollup, query string not
persisted, bots ignored).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import VisitorDaily, VisitorDaySalt, VisitorDayState, WebsiteEvent
from apps.tracker.services import ingest_pageview
from core.mantecato_core import visitor_counting
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries.visitors import read_visit_stats, visit_metrics
from core.mantecato_core.visitor_counting import (
    compute_visitor_key,
    get_or_create_daily_salt,
    record_visit,
    rollup_finished_days,
    utc_day,
)

pytestmark = pytest.mark.django_db

WEBSITE_ID = "a0000000-0000-0000-0000-0000000000aa"


@pytest.fixture(autouse=True)
def _clear_salt_cache():
    """The daily-salt cache is a process global; reset it around each test."""
    visitor_counting._SALT_CACHE.clear()
    yield
    visitor_counting._SALT_CACHE.clear()


def _noon(offset_days: int = 0):
    return (timezone.now() + timedelta(days=offset_days)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )


def _visit(*, ip="1.2.3.4", ua="Mozilla/5.0 Chrome", when=None, is_bot=False, website=WEBSITE_ID):
    record_visit(
        website_id=website,
        occurred_at=when or _noon(),
        ip=ip,
        user_agent=ua,
        is_bot=is_bot,
    )


# --- write path: visit / bounce logic ---------------------------------------


def test_single_pageview_creates_state():
    _visit()
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1
    assert row.cur_visit_pageviews == 1
    assert row.total_pageviews == 1
    assert row.bounces == 0


def test_two_pageviews_same_visit_not_bounce():
    base = _noon()
    _visit(when=base)
    _visit(when=base + timedelta(minutes=5))
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1
    assert row.cur_visit_pageviews == 2
    assert row.total_pageviews == 2
    assert row.cur_visit_duration_s == 300  # 5 minutes accumulated


def test_new_visit_after_timeout_closes_bounce():
    base = _noon()
    _visit(when=base)
    _visit(when=base + timedelta(minutes=45))  # > 30 min idle → new visit
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 2
    assert row.bounces == 1  # first visit had a single pageview
    assert row.cur_visit_pageviews == 1


def test_distinct_visitors_distinct_rows():
    _visit(ip="1.1.1.1")
    _visit(ip="2.2.2.2")
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 2


def test_bot_pageview_not_counted():
    _visit(is_bot=True)
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 0


# --- digest properties ------------------------------------------------------


def test_visitor_key_deterministic_and_input_sensitive():
    salt = get_or_create_daily_salt(utc_day(_noon()))
    k1 = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="1.2.3.4", user_agent="UA")
    k2 = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="1.2.3.4", user_agent="UA")
    k_other_ip = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="9.9.9.9", user_agent="UA")
    assert k1 == k2
    assert k1 != k_other_ip
    assert len(k1) == 64  # hex SHA-256, not raw inputs


# --- read path --------------------------------------------------------------


def test_read_visit_stats_exact_today():
    base = _noon()
    _visit(ip="1.1.1.1", when=base)
    _visit(ip="1.1.1.1", when=base + timedelta(minutes=2))  # same visitor, 2 pv
    _visit(ip="2.2.2.2", when=base)  # single pv → bounce
    stats = read_visit_stats(WEBSITE_ID, base - timedelta(hours=1), base + timedelta(hours=1))
    assert stats["unique_visitors"] == 2
    assert stats["visits"] == 2
    assert stats["bounces"] == 1
    assert stats["total_pageviews"] == 3


def test_visit_metrics_exact_without_filter():
    base = _noon()
    _visit(ip="1.1.1.1", when=base)
    _visit(ip="2.2.2.2", when=base)
    vm = visit_metrics(WEBSITE_ID, base - timedelta(hours=1), base + timedelta(hours=1), [])
    assert vm["visitors"] == 2
    assert vm["visits"] == 2
    assert vm["bounce_rate"] == 100.0  # both single-pageview visits


def test_visit_metrics_suppressed_with_content_filter():
    base = _noon()
    _visit(when=base)
    filters = [Filter(column="browser", operator="eq", value="Chrome")]
    vm = visit_metrics(WEBSITE_ID, base - timedelta(hours=1), base + timedelta(hours=1), filters)
    assert vm["visitors"] is None
    assert vm["visits"] is None
    assert vm["bounce_rate"] is None


# --- rollup + discard (the privacy-critical path) ---------------------------


def test_rollup_finalizes_and_discards_past_day():
    yesterday = _noon(offset_days=-1)
    day = utc_day(yesterday)
    _visit(ip="1.1.1.1", when=yesterday)
    _visit(ip="2.2.2.2", when=yesterday)
    assert VisitorDayState.objects.filter(day=day).count() == 2
    assert VisitorDaySalt.objects.filter(day=day).exists()

    rollup_finished_days()

    daily = VisitorDaily.objects.get(website_id=WEBSITE_ID, day=day, scope="site")
    assert daily.unique_visitors == 2
    assert daily.visits == 2
    assert daily.bounces == 2  # both single-pageview
    # Ephemeral state AND the salt are gone → digests can't be recomputed.
    assert VisitorDayState.objects.filter(day=day).count() == 0
    assert not VisitorDaySalt.objects.filter(day=day).exists()
    # Finalized day is still readable from the permanent aggregate.
    stats = read_visit_stats(
        WEBSITE_ID, yesterday - timedelta(hours=1), yesterday + timedelta(hours=1)
    )
    assert stats["unique_visitors"] == 2


def test_rollup_leaves_today_untouched():
    _visit(when=_noon())
    rollup_finished_days()
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 1
    assert not VisitorDaily.objects.filter(website_id=WEBSITE_ID).exists()


def test_rollup_idempotent():
    yesterday = _noon(offset_days=-1)
    _visit(ip="1.1.1.1", when=yesterday)
    rollup_finished_days()
    rollup_finished_days()  # second run is a no-op
    daily = VisitorDaily.objects.get(website_id=WEBSITE_ID, day=utc_day(yesterday))
    assert daily.unique_visitors == 1  # not double-counted


# --- privacy guarantees -----------------------------------------------------


def test_no_ip_or_user_agent_columns():
    for model in (VisitorDayState, VisitorDaily, WebsiteEvent):
        names = {f.name for f in model._meta.get_fields()}
        assert "ip" not in names
        assert "ip_address" not in names
        assert "user_agent" not in names
        assert "ua" not in names


def test_query_string_not_persisted():
    ingest_pageview(
        website_id=WEBSITE_ID,
        payload={"url": "/checkout?email=user@example.com&token=secret", "title": "Checkout"},
        device_info={"browser": "Chrome", "os": "Mac OS X", "device": "desktop"},
        country=None,
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 Chrome",
    )
    ev = WebsiteEvent.objects.get(website_id=WEBSITE_ID)
    assert ev.url_path == "/checkout"
    assert ev.url_query is None
