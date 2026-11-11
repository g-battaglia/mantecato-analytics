"""RAM-first contracts: bounded Python results and unchanged metric semantics."""

from collections import defaultdict
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db.models.query import QuerySet
from django.utils import timezone

from apps.core.models import VisitorPeriod, WebsiteEvent
from core.mantecato_core.filters import Filter
from core.mantecato_core.queries.stats import _normalize_url
from core.mantecato_core.queries.visitors import read_scope_visitors
from core.mantecato_core.scope_reads import section_uniques
from core.mantecato_core.visitor_counting import section_for_path


@pytest.mark.django_db
@pytest.mark.parametrize("depth", [0, 1, 2, 3, -1, -10])
def test_sql_sections_match_python_normalization_and_distincts(depth, django_assert_num_queries):
    site = uuid4()
    paths = [
        "",
        "/",
        "///",
        "blog/123/item",
        "/blog/123/item",
        "/blog/456/item?x=1",
        "/blog/123/item#title",
        "/blog//item",
        "/blog/12345678901234567890",
        "/BLOG/ABCDEF123456/item",
        "/blog/123e4567-e89b-12d3-a456-426614174000/item",
        "/blog/١٢٣/item",
        "/blog/１２３/item",
        "/blog/𝟘𝟙𝟚/item",
        "/2026/02/03",
        "/same///path/",
        "/index#/?query",
        "/?discard/path",
    ]
    expected = defaultdict(set)
    events = []
    for index, path in enumerate(paths):
        # Repeat visitors across dynamic paths; normalized counts must dedup.
        for key in ("shared", f"visitor-{index}"):
            events.append(WebsiteEvent(website_id=site, url_path=path, visitor_key=key))
            expected[_normalize_url(section_for_path(path, depth))].add(key)
    WebsiteEvent.objects.bulk_create(events)
    wanted = [*expected, "/missing"]
    qs = WebsiteEvent.objects.filter(website_id=site)
    # Regression guard: never transfer per-event digests or accumulate sets.
    with (
        patch.object(QuerySet, "iterator", side_effect=AssertionError("event scan")),
        django_assert_num_queries(1),
    ):
        actual = section_uniques(qs, wanted, depth=depth)
    assert actual == {section: len(keys) for section, keys in expected.items()}


@pytest.mark.django_db
def test_section_counts_keep_site_date_type_country_and_bot_filters():
    site, other = uuid4(), uuid4()
    now = timezone.now()
    for owner, country, bot, event_type, key in [
        (site, "IT", None, 1, "human"),
        (site, "IT", "known_bot_user_agent", 1, "bot"),
        (site, "US", None, 1, "us"),
        (site, "IT", None, 2, "custom"),
        (other, "IT", None, 1, "other"),
        (site, "IT", None, 1, None),
    ]:
        WebsiteEvent.objects.create(
            website_id=owner,
            url_path="/blog/123",
            country=country,
            bot_reason=bot,
            event_type=event_type,
            visitor_key=key,
        )
    old = WebsiteEvent.objects.create(website_id=site, url_path="/blog/123", visitor_key="old")
    WebsiteEvent.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=100))
    filters = [
        Filter("country", "eq", "IT"),
        Filter("__bot_filter__", "eq", '{"config":{"knownBots":true}}'),
    ]
    counts = read_scope_visitors(
        site,
        now - timedelta(seconds=1),
        now + timedelta(minutes=1),
        scope="section",
        scope_values=["/blog/:id"],
        filters=filters,
    )
    assert counts == {"/blog/:id": 1}


@pytest.mark.django_db
def test_section_retention_tail_keeps_depth_and_filter_rules(settings):
    site = uuid4()
    now = timezone.now()
    settings.VISITOR_KEY_RETENTION_DAYS = 1
    old = (now - timedelta(days=70)).date().replace(day=1)
    VisitorPeriod.objects.create(
        website_id=site, period_start=old, scope="section", scope_value="/blog", unique_visitors=7
    )
    start = now - timedelta(days=100)
    assert (
        read_scope_visitors(site, start, now, scope="section", scope_values=["/blog"])["/blog"] == 7
    )
    assert (
        read_scope_visitors(site, start, now, scope="section", scope_values=["/blog"], depth=1)[
            "/blog"
        ]
        == 0
    )
    assert (
        read_scope_visitors(
            site,
            start,
            now,
            scope="section",
            scope_values=["/blog"],
            filters=[Filter("country", "eq", "IT")],
        )["/blog"]
        == 0
    )


@pytest.mark.django_db
def test_empty_section_queryset_never_hits_database(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert section_uniques(WebsiteEvent.objects.none(), ["/blog"]) == {}
        assert section_uniques(WebsiteEvent.objects.all(), []) == {}


def test_overview_skips_unused_live_datasets_and_reuses_countries():
    from tests.test_analytics_overview import TestServiceOrchestration

    fixture = TestServiceOrchestration()
    countries = [{"country": "", "pageviews": 100}]
    countries += [{"country": f"C{i}", "pageviews": 60 - i} for i in range(50)]
    with fixture._patched() as mocks:
        mocks["get_country_breakdown"].return_value = countries
        result = fixture._run(include_live_details=False)
    mocks["get_recent_pageviews"].assert_not_called()
    mocks["get_current_pages"].assert_not_called()
    mocks["get_geo_metrics"].assert_not_called()
    assert mocks["get_country_breakdown"].call_args.kwargs["limit"] == 51
    assert len(result["country"]) == 10
    assert len(result["geo"]) == 50
    assert result["country"][0]["country"] == ""
    assert all(row["country"] for row in result["geo"])
    assert result["geo"][0]["percentage"] == round(60 / sum(range(11, 61)) * 100, 1)
    assert result["country"][0]["pct"] == round(100 / (100 + sum(range(52, 61))) * 100, 1)
    assert all("pct" not in row and "percentage" not in row for row in countries)
