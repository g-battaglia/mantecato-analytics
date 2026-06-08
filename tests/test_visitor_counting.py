"""Tests for the cookieless **exact** visitor/visit/bounce counter.

Covers the compute-and-discard write path (`record_visit`/`record_scope_presence`),
the read path (`read_visit_stats`/`read_scope_visitors`/`visit_metrics`), the
period rollup, and the privacy guarantees. Default exactness window is `month`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import (
    VisitorDaily,
    VisitorDayState,
    VisitorPeriod,
    VisitorSalt,
    VisitorScopeState,
    WebsiteEvent,
)
from apps.tracker.services import ingest_pageview
from core.mantecato_core import visitor_counting
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries.visitors import (
    read_scope_visitors,
    read_visit_stats,
    visit_metrics,
)
from core.mantecato_core.visitor_counting import (
    compute_visitor_key,
    current_period_key,
    get_or_create_salt,
    period_key,
    record_scope_presence,
    record_visit,
    rollup_finished_periods,
    section_for_path,
)

pytestmark = pytest.mark.django_db

WEBSITE_ID = "a0000000-0000-0000-0000-0000000000aa"


@pytest.fixture(autouse=True)
def _clear_salt_cache():
    visitor_counting._SALT_CACHE.clear()
    yield
    visitor_counting._SALT_CACHE.clear()


def _this_month(day: int, hour: int = 12):
    """A datetime on *day* of the current month (day <= 28 for safety)."""
    return timezone.now().replace(day=day, hour=hour, minute=0, second=0, microsecond=0)


def _last_month(day: int = 15, hour: int = 12):
    """A datetime on *day* of the previous month."""
    first_of_this = timezone.now().replace(day=1, hour=hour, minute=0, second=0, microsecond=0)
    return (first_of_this - timedelta(days=1)).replace(day=day)


def _visit(*, ip="1.2.3.4", ua="Mozilla/5.0 Chrome", when=None, path="/", is_bot=False):
    when = when or _this_month(10)
    key = record_visit(
        website_id=WEBSITE_ID,
        occurred_at=when,
        ip=ip,
        user_agent=ua,
        is_bot=is_bot,
        url_path=path,
    )
    if key:
        record_scope_presence(
            website_id=WEBSITE_ID,
            occurred_at=when,
            visitor_key=key,
            scopes=[("page", path), ("section", section_for_path(path))],
        )
    return key


# --- visit / bounce logic ---------------------------------------------------


def test_single_pageview_creates_state():
    _visit()
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1
    assert row.cur_visit_pageviews == 1
    assert row.bounces == 0
    assert row.entry_path == "/"


def test_two_pageviews_same_visit_not_bounce():
    base = _this_month(10)
    _visit(when=base)
    _visit(when=base + timedelta(minutes=5))
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1
    assert row.cur_visit_pageviews == 2
    assert row.cur_visit_duration_s == 300


def test_new_visit_after_timeout_closes_bounce():
    base = _this_month(10)
    _visit(when=base)
    _visit(when=base + timedelta(minutes=45))
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 2
    assert row.bounces == 1


def test_bot_not_counted():
    assert _visit(is_bot=True) is None
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 0


# --- the headline: exact uniques across days of the same window -------------


def test_unique_visitor_exact_across_month():
    # Same visitor on three different days of the current month → ONE unique.
    for d in (10, 15, 20):
        _visit(ip="1.1.1.1", when=_this_month(d))
    stats = read_visit_stats(WEBSITE_ID, _this_month(1), _this_month(28))
    assert stats["unique_visitors"] == 1  # deduped across days (period-stable salt)
    assert stats["visits"] == 3  # three separate days → three visits
    assert stats["bounces"] == 3  # each a single pageview
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 3


def test_distinct_visitors_counted_separately():
    _visit(ip="1.1.1.1", when=_this_month(10))
    _visit(ip="2.2.2.2", when=_this_month(11))
    stats = read_visit_stats(WEBSITE_ID, _this_month(1), _this_month(28))
    assert stats["unique_visitors"] == 2


def test_visit_metrics_suppressed_with_content_filter():
    _visit()
    filters = [Filter(column="browser", operator="eq", value="Chrome")]
    vm = visit_metrics(WEBSITE_ID, _this_month(1), _this_month(28), filters)
    assert vm["visitors"] is None
    assert vm["bounce_rate"] is None


def test_visit_metrics_exact_without_filter():
    _visit(ip="1.1.1.1")
    _visit(ip="2.2.2.2")
    vm = visit_metrics(WEBSITE_ID, _this_month(1), _this_month(28), [])
    assert vm["visitors"] == 2
    assert vm["bounce_rate"] == 100.0


# --- per-scope exact uniques ------------------------------------------------


def test_per_scope_unique_visitors():
    _visit(ip="1.1.1.1", path="/a")
    _visit(ip="2.2.2.2", path="/a")
    _visit(ip="1.1.1.1", path="/b")
    counts = read_scope_visitors(
        WEBSITE_ID, _this_month(1), _this_month(28), scope="page", scope_values=["/a", "/b"]
    )
    assert counts["/a"] == 2
    assert counts["/b"] == 1


# --- rollup + discard (privacy-critical) ------------------------------------


def test_rollup_finalizes_and_discards_past_period():
    when = _last_month(15)
    _visit(ip="1.1.1.1", path="/landing", when=when)
    _visit(ip="2.2.2.2", path="/landing", when=when)
    assert VisitorSalt.objects.filter(period=period_key(when)).exists()

    rollup_finished_periods()

    period_row = VisitorPeriod.objects.get(
        website_id=WEBSITE_ID, scope="site", period_start=when.replace(day=1).date()
    )
    assert period_row.unique_visitors == 2
    # Per-day trend aggregate written too.
    assert VisitorDaily.objects.filter(
        website_id=WEBSITE_ID, scope="site", day=when.date()
    ).exists()
    # Landing-page bounce aggregate.
    landing = VisitorPeriod.objects.get(
        website_id=WEBSITE_ID, scope="landing", scope_value="/landing"
    )
    assert landing.visits == 2
    assert landing.bounces == 2
    # Per-scope page uniques finalised.
    page = VisitorPeriod.objects.get(website_id=WEBSITE_ID, scope="page", scope_value="/landing")
    assert page.unique_visitors == 2
    # Everything ephemeral for that window is discarded.
    assert not VisitorDayState.objects.filter(period=period_key(when)).exists()
    assert not VisitorScopeState.objects.filter(period=period_key(when)).exists()
    assert not VisitorSalt.objects.filter(period=period_key(when)).exists()


def test_rollup_leaves_current_period_untouched():
    _visit(when=_this_month(10))
    rollup_finished_periods()
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 1
    assert not VisitorPeriod.objects.filter(website_id=WEBSITE_ID).exists()


def test_rollup_idempotent():
    _visit(ip="1.1.1.1", when=_last_month(15))
    rollup_finished_periods()
    rollup_finished_periods()
    row = VisitorPeriod.objects.get(website_id=WEBSITE_ID, scope="site")
    assert row.unique_visitors == 1


def test_read_after_rollup_uses_period_aggregate():
    when = _last_month(15)
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        _visit(ip=ip, when=when)
    rollup_finished_periods()
    stats = read_visit_stats(WEBSITE_ID, when.replace(day=1), _last_month(28))
    assert stats["unique_visitors"] == 3


# --- digest + privacy -------------------------------------------------------


def test_visitor_key_deterministic_and_input_sensitive():
    salt = get_or_create_salt(current_period_key())
    k1 = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="1.2.3.4", user_agent="UA")
    k2 = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="1.2.3.4", user_agent="UA")
    k3 = compute_visitor_key(salt, website_id=WEBSITE_ID, ip="9.9.9.9", user_agent="UA")
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 64


def test_no_ip_or_user_agent_columns():
    for model in (VisitorDayState, VisitorScopeState, VisitorDaily, VisitorPeriod, WebsiteEvent):
        names = {f.name for f in model._meta.get_fields()}
        assert "ip" not in names
        assert "ip_address" not in names
        assert "user_agent" not in names
        assert "ua" not in names


def test_visits_by_bucket_day_granularity():
    from core.mantecato_core.queries.visitors import visits_by_bucket

    base = _this_month(10)
    _visit(ip="1.1.1.1", when=base)
    _visit(ip="2.2.2.2", when=base)
    vb = visits_by_bucket(WEBSITE_ID, _this_month(1), _this_month(28), "day")
    assert vb[base.date()] == 2
    # Visits are daily → no series at finer granularity.
    assert visits_by_bucket(WEBSITE_ID, _this_month(1), _this_month(28), "hour") == {}


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
