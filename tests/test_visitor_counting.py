"""Tests for the cookieless **exact** visitor/visit/bounce counter.

Default exactness window is ``day`` (Umami-aligned: unique visitors over a range
= sum of daily uniques). Monthly dedup is verified explicitly via override.
Covers the visit/bounce engine, the read path, the rollup, per-event digests
(hourly visitors, realtime, import attribution), and privacy guarantees.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core.models import (
    VisitorDaily,
    VisitorDayState,
    VisitorPeriod,
    VisitorSalt,
    WebsiteEvent,
)
from apps.tracker.services import ingest_pageview
from core.mantecato_core import visitor_counting
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries.visitors import (
    get_landing_metrics,
    read_scope_visitors,
    read_visit_stats,
    visit_metrics,
    visitors_by_bucket,
    visits_by_bucket,
)
from core.mantecato_core.visitor_counting import (
    aggregate_events_into_daily,
    record_engagement,
    record_scope_presence,
    record_visit,
    rollup_finished_periods,
    section_for_path,
    utc_day,
)

pytestmark = pytest.mark.django_db

WEBSITE_ID = "a0000000-0000-0000-0000-0000000000aa"


@pytest.fixture(autouse=True)
def _clear_salt_cache():
    visitor_counting._SALT_CACHE.clear()
    yield
    visitor_counting._SALT_CACHE.clear()


def _today(hour: int = 12):
    return timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)


def _days_ago(n: int, hour: int = 12):
    return _today(hour) - timedelta(days=n)


def _visit(*, ip="1.2.3.4", ua="Mozilla/5.0 Chrome", when=None, path="/", is_bot=False):
    when = when or _today()
    key = record_visit(
        website_id=WEBSITE_ID, occurred_at=when, ip=ip, user_agent=ua, is_bot=is_bot, url_path=path
    )
    if key:
        record_scope_presence(
            website_id=WEBSITE_ID,
            occurred_at=when,
            visitor_key=key,
            scopes=[("page", path), ("section", section_for_path(path))],
        )
    return key


def _ingest(ip="1.2.3.4", ua="Mozilla/5.0 Chrome", path="/x"):
    ingest_pageview(
        website_id=WEBSITE_ID,
        payload={"url": path, "title": "X"},
        device_info={"browser": "Chrome", "os": "Mac OS X", "device": "desktop"},
        country=None,
        ip=ip,
        user_agent=ua,
    )


def _full_range():
    return _days_ago(40), _today() + timedelta(hours=1)


# --- visit / bounce engine (single day, window-independent) ------------------


def test_single_pageview_creates_state():
    _visit()
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1 and row.cur_visit_pageviews == 1 and row.bounces == 0


def test_two_pageviews_same_visit_not_bounce():
    base = _today()
    _visit(when=base)
    _visit(when=base + timedelta(minutes=5))
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 1 and row.cur_visit_pageviews == 2 and row.cur_visit_duration_s == 300


def test_new_visit_after_timeout_closes_bounce():
    base = _today()
    _visit(when=base)
    _visit(when=base + timedelta(minutes=45))
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.visits == 2 and row.bounces == 1


def test_bot_not_counted():
    assert _visit(is_bot=True) is None
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 0


# --- unique semantics: day window (default) vs month -------------------------


def test_unique_visitors_summed_per_day_default():
    # Same visitor on three different days → with the day window, 3 daily uniques.
    for n in (0, 1, 2):
        _visit(ip="1.1.1.1", when=_days_ago(n))
    s, e = _full_range()
    stats = read_visit_stats(WEBSITE_ID, s, e)
    assert stats["unique_visitors"] == 3
    assert stats["visits"] == 3
    assert stats["bounces"] == 3


@override_settings(VISITOR_EXACT_WINDOW="month")
def test_unique_visitors_monthly_dedup():
    # Same visitor on three days of the same month → ONE unique (month window).
    base = timezone.now().replace(day=10, hour=12, minute=0, second=0, microsecond=0)
    for d in (10, 15, 20):
        _visit(ip="1.1.1.1", when=base.replace(day=d))
    start = base.replace(day=1)
    end = base.replace(day=28) + timedelta(hours=1)
    assert read_visit_stats(WEBSITE_ID, start, end)["unique_visitors"] == 1


def test_distinct_visitors_counted_separately():
    _visit(ip="1.1.1.1", when=_today())
    _visit(ip="2.2.2.2", when=_today())
    s, e = _full_range()
    assert read_visit_stats(WEBSITE_ID, s, e)["unique_visitors"] == 2


def test_visit_metrics_suppressed_with_content_filter():
    _visit()
    filters = [Filter(column="browser", operator="eq", value="Chrome")]
    vm = visit_metrics(WEBSITE_ID, *_full_range(), filters)
    assert vm["visitors"] is None and vm["bounce_rate"] is None


def test_visit_metrics_exact_without_filter():
    _visit(ip="1.1.1.1")
    _visit(ip="2.2.2.2")
    vm = visit_metrics(WEBSITE_ID, *_full_range(), [])
    assert vm["visitors"] == 2 and vm["bounce_rate"] == 100.0


def test_per_scope_unique_visitors():
    _visit(ip="1.1.1.1", path="/a")
    _visit(ip="2.2.2.2", path="/a")
    _visit(ip="1.1.1.1", path="/b")
    counts = read_scope_visitors(
        WEBSITE_ID, *_full_range(), scope="page", scope_values=["/a", "/b"]
    )
    assert counts["/a"] == 2 and counts["/b"] == 1


# --- rollup (day window) ----------------------------------------------------


def test_rollup_finalizes_and_discards_past_day():
    when = _days_ago(1)
    day = utc_day(when)
    _visit(ip="1.1.1.1", when=when)
    _visit(ip="2.2.2.2", when=when)
    rollup_finished_periods()
    daily = VisitorDaily.objects.get(website_id=WEBSITE_ID, scope="site", day=day)
    assert daily.unique_visitors == 2
    period = VisitorPeriod.objects.get(website_id=WEBSITE_ID, scope="site", period_start=day)
    assert period.unique_visitors == 2
    assert not VisitorDayState.objects.filter(day=day).exists()
    assert not VisitorSalt.objects.filter(period=day.isoformat()).exists()
    # Still readable from the finalised aggregate.
    assert read_visit_stats(WEBSITE_ID, when - timedelta(hours=1), when + timedelta(hours=1))[
        "unique_visitors"
    ] == 2


def test_rollup_leaves_current_day_untouched():
    _visit(when=_today())
    rollup_finished_periods()
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 1


def test_rollup_idempotent():
    _visit(ip="1.1.1.1", when=_days_ago(1))
    rollup_finished_periods()
    rollup_finished_periods()
    assert VisitorPeriod.objects.get(website_id=WEBSITE_ID, scope="site").unique_visitors == 1


# --- import attribution: aggregate events into daily ------------------------


def test_aggregate_imported_events_into_daily():
    # Imported pageviews: website_event rows with visitor_key, NO VisitorDayState.
    when = _days_ago(3)
    for ip_key, n_pv in [("sessA", 2), ("sessB", 1)]:
        for _ in range(n_pv):
            ev = WebsiteEvent.objects.create(
                website_id=WEBSITE_ID, url_path="/x", event_type=1, visitor_key=ip_key
            )
            WebsiteEvent.objects.filter(pk=ev.pk).update(created_at=when)
    res = aggregate_events_into_daily(WEBSITE_ID)
    assert res["days"] == 1
    daily = VisitorDaily.objects.get(website_id=WEBSITE_ID, scope="site", day=utc_day(when))
    assert daily.unique_visitors == 2  # two sessions
    assert daily.total_pageviews == 3
    assert daily.visits >= 2 and daily.visits <= daily.total_pageviews  # visits <= pageviews
    # Digests discarded after aggregation.
    assert not WebsiteEvent.objects.filter(
        website_id=WEBSITE_ID, visitor_key__isnull=False
    ).exists()
    # And read picks it up.
    assert read_visit_stats(WEBSITE_ID, when - timedelta(hours=1), when + timedelta(hours=1))[
        "unique_visitors"
    ] == 2


# --- per-event digest: hourly visitors + realtime + privacy -----------------


def test_visitors_by_bucket_hourly():
    _ingest(ip="1.1.1.1")
    _ingest(ip="2.2.2.2")
    _ingest(ip="1.1.1.1")
    now = timezone.now()
    vb = visitors_by_bucket(WEBSITE_ID, now - timedelta(hours=1), now + timedelta(hours=1), "hour")
    assert sum(vb.values()) == 2


def test_realtime_visitors_online():
    from core.mantecato_core.queries.realtime import get_active_pageviews

    _ingest(ip="1.1.1.1")
    _ingest(ip="2.2.2.2")
    _ingest(ip="1.1.1.1")
    rt = get_active_pageviews(WEBSITE_ID)
    assert rt["count"] == 3 and rt["visitors"] == 2


def test_no_ip_or_user_agent_columns():
    for model in (VisitorDayState, VisitorDaily, VisitorPeriod, WebsiteEvent):
        names = {f.name for f in model._meta.get_fields()}
        assert "ip" not in names and "ip_address" not in names
        assert "user_agent" not in names and "ua" not in names


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
    assert ev.url_path == "/checkout" and ev.url_query is None


# --- engagement: real on-page time + engaged bounce -------------------------


def test_engagement_makes_single_page_not_bounce():
    # One pageview + an engagement beacon ≥ threshold → real duration, no bounce.
    base = _today()
    _visit(ip="1.2.3.4", when=base)
    record_engagement(
        website_id=WEBSITE_ID,
        occurred_at=base + timedelta(seconds=5),
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 Chrome",
        seconds=30,
    )
    stats = read_visit_stats(WEBSITE_ID, *_full_range())
    assert stats["visits"] == 1
    assert stats["bounces"] == 0  # engaged 30s ≥ 10s threshold → not a bounce
    assert stats["total_duration_s"] == 30


def test_engagement_below_threshold_still_bounces():
    base = _today()
    _visit(ip="1.2.3.4", when=base)
    record_engagement(
        website_id=WEBSITE_ID,
        occurred_at=base + timedelta(seconds=2),
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 Chrome",
        seconds=3,
    )
    stats = read_visit_stats(WEBSITE_ID, *_full_range())
    assert stats["bounces"] == 1  # only 3s active < 10s threshold → bounce


def test_engagement_without_pageview_is_noop():
    record_engagement(
        website_id=WEBSITE_ID,
        occurred_at=_today(),
        ip="9.9.9.9",
        user_agent="X",
        seconds=20,
    )
    assert VisitorDayState.objects.filter(website_id=WEBSITE_ID).count() == 0


def test_engagement_after_timeout_is_noop():
    base = _today()
    _visit(ip="1.2.3.4", when=base)
    record_engagement(
        website_id=WEBSITE_ID,
        occurred_at=base + timedelta(minutes=45),
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 Chrome",
        seconds=60,
    )
    row = VisitorDayState.objects.get(website_id=WEBSITE_ID)
    assert row.cur_page_engaged_s == 0  # stale beacon ignored, visit not revived


# --- landing (entry) pages + visits-by-bucket -------------------------------


def test_landing_metrics_visits_and_bounce():
    base = _today()
    _visit(ip="1.1.1.1", path="/a", when=base)  # single page → bounce
    _visit(ip="2.2.2.2", path="/b", when=base)
    _visit(ip="2.2.2.2", path="/b/2", when=base + timedelta(minutes=2))  # 2 pv → no bounce
    rows = get_landing_metrics(WEBSITE_ID, *_full_range())
    by_entry = {r["entry_path"]: r for r in rows}
    assert by_entry["/a"]["visits"] == 1 and by_entry["/a"]["bounce_rate"] == 100.0
    assert by_entry["/b"]["visits"] == 1 and by_entry["/b"]["bounce_rate"] == 0.0


def test_visits_by_bucket_counts_sessions():
    _ingest(ip="1.1.1.1")
    _ingest(ip="2.2.2.2")
    _ingest(ip="1.1.1.1")  # same visitor, same visit
    now = timezone.now()
    vb = visits_by_bucket(WEBSITE_ID, now - timedelta(hours=1), now + timedelta(hours=1), "hour")
    assert sum(vb.values()) == 2  # two distinct visits


def test_live_ua_bot_toggle_current_period():
    # A UA bot ingested in the CURRENT (un-rolled) period is toggleable in real time.
    base = _today()
    _visit(ip="1.1.1.1", when=base)  # human → VisitorDayState (live)
    ev = WebsiteEvent.objects.create(
        website_id=WEBSITE_ID, url_path="/x", event_type=1, is_bot=True, visitor_key="botlive"
    )
    WebsiteEvent.objects.filter(pk=ev.pk).update(created_at=base)
    s, e = base - timedelta(hours=1), base + timedelta(hours=1)
    assert read_visit_stats(WEBSITE_ID, s, e, bot_filter_on=True)["unique_visitors"] == 1  # human
    assert read_visit_stats(WEBSITE_ID, s, e, bot_filter_on=False)["unique_visitors"] == 2  # + bot


def test_rollup_ua_bot_split_and_toggle():
    # A UA/datacenter bot (is_bot at ingest) is counted separately and toggleable.
    when = _days_ago(1)
    day = utc_day(when)
    _visit(ip="1.1.1.1", when=when)  # human → VisitorDayState
    ev = WebsiteEvent.objects.create(
        website_id=WEBSITE_ID, url_path="/x", event_type=1, is_bot=True, visitor_key="botkey"
    )
    WebsiteEvent.objects.filter(pk=ev.pk).update(created_at=when)

    rollup_finished_periods()

    daily = VisitorDaily.objects.get(website_id=WEBSITE_ID, scope="site", day=day)
    assert daily.unique_visitors == 1 and daily.bot_unique_visitors == 1
    s, e = when - timedelta(hours=1), when + timedelta(hours=1)
    assert read_visit_stats(WEBSITE_ID, s, e, bot_filter_on=True)["unique_visitors"] == 1
    assert read_visit_stats(WEBSITE_ID, s, e, bot_filter_on=False)["unique_visitors"] == 2


def test_imported_per_scope_unique_visitors():
    when = _days_ago(3)
    for ip_key, paths in [("sessA", ["/x", "/x"]), ("sessB", ["/x", "/y"])]:
        for p in paths:
            ev = WebsiteEvent.objects.create(
                website_id=WEBSITE_ID, url_path=p, event_type=1, visitor_key=ip_key
            )
            WebsiteEvent.objects.filter(pk=ev.pk).update(created_at=when)
    aggregate_events_into_daily(WEBSITE_ID)
    counts = read_scope_visitors(
        WEBSITE_ID, *_full_range(), scope="page", scope_values=["/x", "/y"]
    )
    assert counts["/x"] == 2 and counts["/y"] == 1
