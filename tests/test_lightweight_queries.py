"""Performance contracts and result parity, using isolated PostgreSQL."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from itertools import groupby
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.api.v1.contracts import parse_query
from apps.api.v1.queries.analytics import _aggregate_sql
from apps.api.v1.services import run_query
from apps.core.models import WebsiteEvent
from core.mantecato_core.visitor_counting import event_landing_stats, event_visitor_stats
from core.mantecato_core.visitor_reads import session_buckets

SITE = uuid.UUID("b0000000-0000-0000-0000-000000000002")


@pytest.mark.parametrize(
    "metrics,has_distinct,has_sessions",
    [
        (["pageviews"], False, False),
        (["human_pageviews", "bot_pageviews"], False, False),
        (["events"], False, False),
        (["daily_unique_visitors"], True, False),
        (["visits", "bounces", "total_duration"], False, True),
        (["pages_per_visit", "daily_unique_visitors"], True, True),
    ],
)
def test_metric_dependencies_generate_only_needed_sql(metrics, has_distinct, has_sessions):
    spec = parse_query({"website_id": str(SITE), "metrics": metrics})
    sql, _ = _aggregate_sql(spec, hard_limit=100)
    assert ("LAG(" in sql) is has_sessions
    assert ("COUNT(DISTINCT" in sql) is has_distinct


def test_totals_are_not_computed_twice():
    spec = parse_query({"website_id": str(SITE), "operation": "totals", "metrics": ["pageviews"]})
    with patch("apps.api.v1.services.aggregate", return_value=([{"pageviews": 7}], False)) as q:
        result = run_query(spec)
    assert q.call_count == 1
    assert result["totals"] == {"pageviews": 7}


def test_overlapping_dimensions_keep_independent_totals():
    spec = parse_query(
        {
            "website_id": str(SITE),
            "operation": "breakdown",
            "dimensions": ["content_group"],
            "metrics": ["pageviews"],
        }
    )
    with patch(
        "apps.api.v1.services.aggregate",
        side_effect=[
            (
                [{"content_group": "a", "pageviews": 7}, {"content_group": "b", "pageviews": 7}],
                False,
            ),
            ([{"pageviews": 7}], False),
        ],
    ) as q:
        result = run_query(spec)
    assert q.call_count == 2
    assert result["totals"]["pageviews"] == 7


@pytest.mark.django_db
def test_dashboard_sql_preserves_legacy_sessions_and_integer_duration():
    rng = random.Random(42)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for key in ("a", "b", "c", None):
        when = start
        for i in range(40):
            when += timedelta(seconds=rng.choice([0, 0.75, 15.3, 1800.9, 1801, 2000]))
            row = WebsiteEvent.objects.create(
                website_id=SITE,
                url_path=f"/p/{i % 3}",
                visitor_key=key,
            )
            WebsiteEvent.objects.filter(pk=row.pk).update(created_at=when)
    qs = WebsiteEvent.objects.filter(website_id=SITE)
    expected = dict(unique_visitors=0, visits=0, bounces=0, total_pageviews=0, total_duration_s=0)
    landings = {}
    buckets = {}
    rows = qs.order_by("visitor_key", "created_at", "event_id").values_list(
        "visitor_key", "created_at", "url_path"
    )
    for _, group in groupby(rows, key=lambda row: row[0]):
        hits = list(group)
        expected["unique_visitors"] += 1
        expected["total_pageviews"] += len(hits)
        n = 0
        previous = None
        landing = None
        for _, when, path in hits:
            gap = None if previous is None else (when - previous).total_seconds()
            if gap is None or int(gap) > 1800:
                if n == 1:
                    expected["bounces"] += 1
                expected["visits"] += 1
                n = 1
            else:
                n += 1
                expected["total_duration_s"] += int(gap)
            if gap is None or int(gap) > 1800:
                landing = path
                landings.setdefault(landing, dict(visits=0, bounces=0))["visits"] += 1
                landings[landing]["bounces"] += 1
                landing_pv = 1
            else:
                if landing_pv == 1:
                    landings[landing]["bounces"] -= 1
                landing_pv += 1
            if gap is None or gap > 1800:
                bucket = when.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                buckets[bucket] = buckets.get(bucket, 0) + 1
            previous = when
        if n == 1:
            expected["bounces"] += 1
    with CaptureQueriesContext(connection) as queries:
        actual = event_visitor_stats(qs)
    assert actual == expected
    assert len(queries) == 1
    assert event_landing_stats(qs) == landings
    assert session_buckets(qs, "day") == buckets
    assert event_visitor_stats(qs.none())["visits"] == 0
    assert event_landing_stats(qs.none()) == {}
