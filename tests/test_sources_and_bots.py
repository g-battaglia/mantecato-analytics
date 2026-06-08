"""Traffic sources (referrer **domain** only) and datacenter-IP bot detection.

Referrers are reduced to their bare domain at ingestion — the full URL, query
string and any UTM/click IDs are never stored. Datacenter/cloud source IPs are
flagged as bots from a bundled CIDR list with no external calls; the IP itself is
never persisted.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core.models import WebsiteEvent
from apps.tracker.services import _referrer_domain, ingest_pageview
from apps.tracker.ua import classify_bot_user_agent
from core.mantecato_core import ip_reputation
from core.mantecato_core.bot_sessions import compute_bot_visitor_keys
from core.mantecato_core.filters import build_bot_filter_sql
from core.mantecato_core.ip_reputation import is_datacenter_ip
from core.mantecato_core.queries.sources import get_referrer_metrics

pytestmark = pytest.mark.django_db

WEBSITE_ID = "a0000000-0000-0000-0000-0000000000aa"


def _full_range():
    now = timezone.now()
    return now - timedelta(days=2), now + timedelta(hours=1)


def _ingest(referrer, *, hostname="example.com", path="/p"):
    ingest_pageview(
        website_id=WEBSITE_ID,
        payload={"url": path, "title": "P", "hostname": hostname, "referrer": referrer},
        device_info={"browser": "Chrome", "os": "Mac OS X", "device": "desktop"},
        country=None,
        ip="1.2.3.4",
        user_agent="Mozilla/5.0 Chrome",
    )


# --- referrer domain reduction ----------------------------------------------


def test_referrer_domain_reduces_to_host():
    assert _referrer_domain("https://www.google.com/search?q=secret", "example.com") == "google.com"


def test_referrer_domain_self_referral_is_none():
    assert _referrer_domain("https://example.com/a", "example.com") is None
    assert _referrer_domain("https://www.example.com/a", "www.example.com") is None


def test_referrer_domain_empty_is_none():
    assert _referrer_domain("", "example.com") is None
    assert _referrer_domain(None, "example.com") is None


def test_ingest_stores_referrer_domain_only():
    _ingest("https://news.ycombinator.com/item?id=1&utm_source=x")
    ev = WebsiteEvent.objects.get(website_id=WEBSITE_ID)
    assert ev.referrer_domain == "news.ycombinator.com"


def test_ingest_self_referral_stored_as_none():
    _ingest("https://example.com/other", hostname="example.com")
    ev = WebsiteEvent.objects.get(website_id=WEBSITE_ID)
    assert ev.referrer_domain is None


def test_get_referrer_metrics_groups_by_domain():
    _ingest("https://google.com/a")
    _ingest("https://google.com/b")
    _ingest("https://bing.com/c")
    rows = get_referrer_metrics(WEBSITE_ID, *_full_range())
    by = {r["referrer"]: r["pageviews"] for r in rows}
    assert by["google.com"] == 2
    assert by["bing.com"] == 1


# --- datacenter IP reputation -----------------------------------------------


@override_settings(DATACENTER_CIDRS=[])
def test_is_datacenter_ip():
    ip_reputation.reload_ranges()
    assert is_datacenter_ip("20.1.2.3") is True  # Azure 20.0.0.0/8
    assert is_datacenter_ip("192.0.2.10") is False  # TEST-NET, not a datacenter
    assert is_datacenter_ip(None) is False
    assert is_datacenter_ip("not-an-ip") is False


@override_settings(DATACENTER_CIDRS=["198.51.100.0/24"])
def test_datacenter_cidrs_extendable():
    ip_reputation.reload_ranges()
    try:
        assert is_datacenter_ip("198.51.100.5") is True
    finally:
        ip_reputation.reload_ranges()


def test_expanded_bot_user_agents():
    assert classify_bot_user_agent("HeadlessChrome/120.0")[0] is True
    assert classify_bot_user_agent("python-requests/2.31")[0] is True
    assert classify_bot_user_agent("Scrapy/2.11 (+https://scrapy.org)")[0] is True
    assert classify_bot_user_agent("Mozilla/5.0 (Macintosh) Chrome/120 Safari/537")[0] is False


def test_datacenter_ip_in_default_bot_filter():
    result = build_bot_filter_sql({})
    assert "datacenter_ip" in result["params"]["botReasons"]


# --- behavioural bot classification on the cookieless digest (v3 parity) -----


def _make_events(visitor_key, n, base, *, gap_minutes=0, browser="Chrome", os="Mac OS X"):
    for i in range(n):
        ev = WebsiteEvent.objects.create(
            website_id=WEBSITE_ID,
            url_path="/x",
            event_type=1,
            visitor_key=visitor_key,
            browser=browser,
            os=os,
            country="US",
            device="desktop",
        )
        WebsiteEvent.objects.filter(pk=ev.pk).update(
            created_at=base + timedelta(minutes=gap_minutes * i)
        )


def test_compute_bot_visitor_keys_zero_engagement():
    base = timezone.now() - timedelta(days=1)
    _make_events("sessA", 1, base)  # single page, dur 0 → bot
    _make_events("sessB", 2, base, gap_minutes=5)  # 2 pages, dur > 0 → human
    bots = compute_bot_visitor_keys(
        WEBSITE_ID, None, None, {"enabled": True, "zeroEngagement": True}
    )
    assert bots == {"sessA"}


def test_compute_bot_visitor_keys_disabled_returns_empty():
    _make_events("sessA", 1, timezone.now() - timedelta(days=1))
    assert (
        compute_bot_visitor_keys(
            WEBSITE_ID, None, None, {"enabled": False, "zeroEngagement": True}
        )
        == set()
    )


def test_compute_bot_visitor_keys_engaged_single_page_not_bot():
    # A single-page visit with real engaged time is NOT a zero-engagement bot.
    base = timezone.now() - timedelta(days=1)
    _make_events("sessA", 1, base)
    bots = compute_bot_visitor_keys(
        WEBSITE_ID,
        None,
        None,
        {"enabled": True, "zeroEngagement": True},
        engaged_dur_by_key={"sessA": 30.0},
    )
    assert bots == set()


def _make_event(visitor_key, base, **fields):
    defaults = {
        "website_id": WEBSITE_ID,
        "url_path": "/x",
        "event_type": 1,
        "visitor_key": visitor_key,
        "country": "US",
        "browser": "Chrome",
        "os": "Mac OS X",
        "device": "desktop",
    }
    defaults.update(fields)
    ev = WebsiteEvent.objects.create(**defaults)
    WebsiteEvent.objects.filter(pk=ev.pk).update(created_at=base)


def test_bot_filter_country_and_ua_at_read_time():
    # Visitors are read from the event digests, so the bot filter (and a country
    # exclusion) applies downstream at read time. The stored data never changes.
    import json

    from core.mantecato_core.filters import Filter
    from core.mantecato_core.queries.visitors import read_visit_stats

    base = timezone.now() - timedelta(days=1)
    _make_events("human", 2, base, gap_minutes=5)  # human (US)
    _make_event("botua", base, is_bot=True, bot_reason="known_bot_user_agent", browser="bot", os="")
    _make_event("sg1", base, country="SG")  # Singapore visitor

    s, e = base - timedelta(hours=1), base + timedelta(hours=1)
    assert read_visit_stats(WEBSITE_ID, s, e)["unique_visitors"] == 3  # no filter → all

    # Known-bot filter excludes the UA bot.
    bf = Filter(
        column="__bot_filter__",
        operator="eq",
        value=json.dumps({"config": {"enabled": True, "knownBots": True}}),
    )
    assert read_visit_stats(WEBSITE_ID, s, e, [bf])["unique_visitors"] == 2

    # Excluding Singapore drops that visitor (the exact case reported).
    bf_sg = Filter(
        column="__bot_filter__",
        operator="eq",
        value=json.dumps(
            {
                "config": {
                    "enabled": True,
                    "knownBots": False,
                    "emptyUa": False,
                    "datacenterIps": False,
                    "excludedCountries": ["SG"],
                }
            }
        ),
    )
    assert read_visit_stats(WEBSITE_ID, s, e, [bf_sg])["unique_visitors"] == 2

    # The stored data is unchanged by the filter.
    assert WebsiteEvent.objects.filter(website_id=WEBSITE_ID).count() == 4


def test_visit_metrics_country_filter_moves_visitors():
    # The exact dashboard path: a content filter (country) now moves the visitor KPI.
    from core.mantecato_core.filters import Filter
    from core.mantecato_core.queries.visitors import visit_metrics

    base = timezone.now() - timedelta(days=1)
    _make_event("us1", base, country="US")
    _make_event("sg1", base, country="SG")
    s, e = base - timedelta(hours=1), base + timedelta(hours=1)

    assert visit_metrics(WEBSITE_ID, s, e, [])["visitors"] == 2
    only_us = [Filter(column="country", operator="eq", value="US")]
    assert visit_metrics(WEBSITE_ID, s, e, only_us)["visitors"] == 1
