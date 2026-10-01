"""Real PostgreSQL regression tests for offline maintenance and hot-path isolation."""

from __future__ import annotations

import io
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import (
    VisitorDaily,
    VisitorDayState,
    VisitorPeriod,
    VisitorSalt,
    VisitorScopeState,
    WebsiteEvent,
)
from apps.tracker.services import ingest_pageview
from core.mantecato_core.visitor_counting import _ROLLUP_LOCK_KEY
from core.mantecato_core.visitor_rollup import MaintenanceBusy, expire_digests, run_rollup

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SITE = uuid.UUID("a0000000-0000-0000-0000-0000000000aa")
OTHER = uuid.UUID("b0000000-0000-0000-0000-0000000000bb")
pytestmark = pytest.mark.django_db(transaction=True)


def state(site=SITE, key="a", period="2026-09", day=None):
    day = day or NOW - timedelta(days=3)
    return VisitorDayState.objects.create(
        website_id=site,
        day=day.date(),
        period=period,
        visitor_key=key,
        first_seen=day,
        last_seen=day,
        entry_path="/a",
    )


def scope(site=SITE, key="a", value="/a", period="2026-09"):
    return VisitorScopeState.objects.create(
        website_id=site,
        visitor_key=key,
        period=period,
        scope="page",
        scope_value=value,
    )


def test_ingest_at_month_boundary_does_no_housekeeping():
    old = state()
    with (
        patch("core.mantecato_core.visitor_rollup.run_rollup") as rollup,
        patch("core.mantecato_core.visitor_rollup.expire_digests") as expiry,
        patch("apps.tracker.services.record_visit", side_effect=RuntimeError("fold failed")),
    ):
        ingest_pageview(str(SITE), {"url": "/new"}, {}, None)
    rollup.assert_not_called()
    expiry.assert_not_called()
    assert VisitorDayState.objects.filter(pk=old.pk).exists()
    assert WebsiteEvent.objects.filter(website_id=SITE, url_path="/new").count() == 1


def test_set_based_formulas_and_existing_additive_counts():
    a = state(key="a")
    a.visits = 2
    a.bounces = 1
    a.total_pageviews = 3
    a.cur_page_engaged_s = 15
    a.total_duration_s = 20
    a.save()
    state(key="b")
    scope(key="a")
    scope(key="b")
    VisitorDaily.objects.create(
        website_id=SITE,
        day=a.day,
        unique_visitors=4,
        visits=4,
        total_pageviews=4,
    )
    result = run_rollup(NOW)
    assert result["status"] == "completed"
    row = VisitorDaily.objects.get(website_id=SITE)
    assert (
        row.unique_visitors,
        row.visits,
        row.bounces,
        row.total_pageviews,
        row.total_duration_s,
    ) == (6, 7, 2, 8, 35)
    landing = VisitorPeriod.objects.get(website_id=SITE, scope="landing")
    assert (landing.visits, landing.bounces) == (2, 1)
    page = VisitorPeriod.objects.get(website_id=SITE, scope="page")
    assert page.unique_visitors == 2
    run_rollup(NOW)
    row.refresh_from_db()
    assert row.unique_visitors == 6


def test_abort_rolls_back_aggregate_and_source_deletion():
    old = state()
    scope()
    expired = WebsiteEvent.objects.create(website_id=SITE, url_path="/", visitor_key="aged")
    WebsiteEvent.objects.filter(pk=expired.pk).update(created_at=NOW - timedelta(days=400))
    from core.mantecato_core.visitor_rollup import _rollup_unit

    def fail_after_writes(*args):
        _rollup_unit(*args)
        raise RuntimeError("injected crash")

    with (
        patch("core.mantecato_core.visitor_rollup._rollup_unit", fail_after_writes),
        pytest.raises(RuntimeError),
    ):
        run_rollup(NOW)
    assert VisitorDayState.objects.filter(pk=old.pk).exists()
    assert VisitorScopeState.objects.exists()
    assert not VisitorDaily.objects.exists()
    expired.refresh_from_db()
    assert expired.visitor_key is None  # Retention commits independently of the failed unit.
    run_rollup(NOW)
    assert VisitorDaily.objects.get().unique_visitors == 1


def test_completed_units_survive_crash_and_shared_salt_is_kept():
    state()
    state(site=OTHER)
    VisitorSalt.objects.create(period="2026-09", salt=b"a" * 32)
    from core.mantecato_core.visitor_rollup import _rollup_unit

    def fail_second(site, *args):
        if site == str(OTHER):
            raise RuntimeError("second unit failed")
        _rollup_unit(site, *args)

    with (
        patch("core.mantecato_core.visitor_rollup._rollup_unit", fail_second),
        pytest.raises(RuntimeError),
    ):
        run_rollup(NOW)
    assert VisitorDaily.objects.filter(website_id=SITE).get().unique_visitors == 1
    assert not VisitorDayState.objects.filter(website_id=SITE).exists()
    assert VisitorDayState.objects.filter(website_id=OTHER).exists()
    assert VisitorSalt.objects.filter(period="2026-09").exists()
    run_rollup(NOW)
    assert not VisitorSalt.objects.exists()
    assert VisitorDaily.objects.filter(website_id=SITE).get().unique_visitors == 1


def test_legacy_week_keeps_landing_months_before_root_normalization():
    first = state(key="a", period="2026-W40", day=datetime(2026, 9, 30, tzinfo=UTC))
    second = state(key="b", period="2026-W40", day=datetime(2026, 10, 1, tzinfo=UTC))
    first.entry_path = ""
    first.save()
    second.entry_path = "/"
    second.save()
    run_rollup(datetime(2026, 11, 1, tzinfo=UTC))
    landings = list(VisitorPeriod.objects.filter(scope="landing").order_by("period_start"))
    assert [row.period_start.month for row in landings] == [9, 10]
    assert [row.scope_value for row in landings] == ["/", "/"]
    assert [row.visits for row in landings] == [1, 1]


def test_scope_only_orphan_salts_and_current_legacy_keys():
    scope()
    VisitorSalt.objects.create(period="2026-09", salt=b"a" * 32)
    VisitorSalt.objects.create(period="2026-08", salt=b"b" * 32)
    live = state(period="2026-10-01", day=NOW)
    bad = state(key="bad", period="2026-13", day=NOW)
    result = run_rollup(NOW)
    assert result["scope_rows"] == 1
    assert result["salts"] == 2
    assert VisitorPeriod.objects.get(scope="page").unique_visitors == 1
    assert VisitorDayState.objects.filter(pk__in=[live.pk, bad.pk]).count() == 2


def test_lock_busy_on_independent_connection_shared_with_import():
    state()
    with psycopg.connect(**connection.get_connection_params()) as other:
        other.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])
        before = time.monotonic()
        result = run_rollup(NOW)
        assert time.monotonic() - before < 2
        assert result["status"] == "busy"
        assert result["remaining_units"] == 1
        assert VisitorDayState.objects.exists()
    assert run_rollup(NOW)["status"] == "completed"


def test_retention_cannot_erase_backfill_inputs_while_shared_lock_is_busy():
    event = WebsiteEvent.objects.create(website_id=SITE, url_path="/imported", visitor_key="old")
    WebsiteEvent.objects.filter(pk=event.pk).update(created_at=NOW - timedelta(days=400))
    with psycopg.connect(**connection.get_connection_params()) as backfill:
        backfill.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])
        result = run_rollup(NOW)
        assert result["status"] == "busy"
        assert result["expired_digests"] == 0
        assert result["retention_pending"] is True
        event.refresh_from_db()
        assert event.visitor_key == "old"
        assert not VisitorDaily.objects.exists()
        with pytest.raises(MaintenanceBusy):
            expire_digests(NOW)
    assert run_rollup(NOW)["expired_digests"] == 1


def test_retention_releases_lock_between_batches_and_reports_committed_progress():
    from core.mantecato_core.visitor_rollup import _try_lock

    for i in range(5):
        event = WebsiteEvent.objects.create(website_id=SITE, url_path="/old", visitor_key=str(i))
        WebsiteEvent.objects.filter(pk=event.pk).update(created_at=NOW - timedelta(days=400))
    calls = 0
    expire = expire_digests
    with psycopg.connect(**connection.get_connection_params()) as backfill:

        def lock():
            nonlocal calls
            calls += 1
            if calls == 2:
                backfill.execute("SELECT pg_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])
            return _try_lock()

        def small_batches(*args, **kwargs):
            return expire(*args, **kwargs, batch_size=2)

        with (
            patch("core.mantecato_core.visitor_rollup._try_lock", side_effect=lock),
            patch("core.mantecato_core.visitor_rollup.expire_digests", small_batches),
        ):
            result = run_rollup(NOW)
        assert result["status"] == "busy"
        assert result["expired_digests"] == 2
        assert result["retention_pending"] is True
        assert WebsiteEvent.objects.filter(visitor_key__isnull=False).count() == 3
    assert run_rollup(NOW)["expired_digests"] == 3


def test_dry_run_and_selector_leave_everything_intact():
    state()
    state(site=OTHER)
    result = run_rollup(NOW, website_id=SITE, dry_run=True)
    assert result["remaining_units"] == 1
    assert VisitorDayState.objects.count() == 2
    run_rollup(NOW, website_id=SITE, period="2026-09")
    assert VisitorDayState.objects.filter(website_id=OTHER).exists()


def test_retention_batches_work_without_a_finished_window():
    for i in range(7):
        row = WebsiteEvent.objects.create(website_id=SITE, url_path="/", visitor_key=str(i))
        WebsiteEvent.objects.filter(pk=row.pk).update(created_at=NOW - timedelta(days=400))
    assert expire_digests(NOW, batch_size=2) == 7
    assert WebsiteEvent.objects.count() == 7
    assert not WebsiteEvent.objects.filter(visitor_key__isnull=False).exists()
    assert run_rollup(NOW)["status"] == "completed"


def test_rollup_query_count_does_not_grow_per_scope():
    def measured(n):
        state()
        for i in range(n):
            scope(value=f"/p/{i}")
        with CaptureQueriesContext(connection) as queries:
            run_rollup(NOW)
        return len(queries)

    small = measured(1)
    large = measured(100)
    assert large == small
    assert large < 60


def test_command_reports_incomplete_and_validates_options():
    with (
        patch(
            "apps.core.management.commands.rollup_visitors.rollup_finished_periods",
            return_value={"status": "busy"},
        ),
        pytest.raises(CommandError) as exc,
    ):
        call_command("rollup_visitors", stdout=io.StringIO())
    assert exc.value.returncode == 2
    with pytest.raises(CommandError):
        call_command("rollup_visitors", period="2026-13")
    with pytest.raises(CommandError):
        call_command("rollup_visitors", max_runtime=0)


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), -1])
def test_nonfinite_or_negative_budget_is_rejected(budget):
    with pytest.raises(ValueError):
        run_rollup(NOW, max_runtime=budget)
    with pytest.raises(CommandError):
        call_command("rollup_visitors", max_runtime=budget)


def test_command_dry_run_does_not_delete_source():
    state()
    output = io.StringIO()
    call_command("rollup_visitors", dry_run=True, stdout=output)
    assert '"status": "dry_run"' in output.getvalue()
    assert VisitorDayState.objects.exists()


def test_concurrent_visit_upserts_never_lose_counts():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from core.mantecato_core.visitor_counting import (
        record_engagement,
        record_visit,
        visitor_key_for,
    )

    visitor_key_for(website_id=str(SITE), occurred_at=NOW, ip="1.2.3.4", user_agent="test")

    def worker(_):
        try:
            for i in range(10):
                record_visit(
                    website_id=str(SITE),
                    occurred_at=NOW,
                    ip="1.2.3.4",
                    user_agent="test",
                    is_bot=False,
                    url_path="/parallel",
                )
                record_engagement(
                    website_id=str(SITE),
                    occurred_at=NOW,
                    ip="1.2.3.4",
                    user_agent="test",
                    seconds=i,
                )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(worker, range(4)))
    row = VisitorDayState.objects.get(website_id=SITE)
    assert row.total_pageviews == 40
    assert row.cur_visit_pageviews == 40
    assert row.visits == 1


def test_budget_exhaustion_commits_first_unit_only():
    state()
    state(site=OTHER)
    from core.mantecato_core.visitor_rollup import _rollup_unit

    def slow_unit(*args):
        _rollup_unit(*args)
        time.sleep(0.03)

    with patch("core.mantecato_core.visitor_rollup._rollup_unit", slow_unit):
        result = run_rollup(NOW, max_runtime=0.02)
    assert result["status"] == "budget_exhausted"
    assert result["periods"] == 1
    assert result["remaining_units"] == 1
    assert VisitorDaily.objects.filter(website_id=SITE).exists()
    assert run_rollup(NOW)["status"] == "completed"
