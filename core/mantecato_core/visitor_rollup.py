"""Offline, bounded PostgreSQL maintenance. Never called by HTTP ingestion.

Each site/finished-period is committed independently. Aggregate increments and
source deletion share a transaction: retries cannot add the same source twice.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import timedelta
from math import isfinite
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

logger = logging.getLogger(__name__)
_COUNTERS = ("unique_visitors", "visits", "bounces", "total_pageviews", "total_duration_s")


class MaintenanceBusy(RuntimeError):
    """Another maintenance/import transaction owns the shared lock."""

    def __init__(self, expired_digests: int = 0) -> None:
        super().__init__("Maintenance lock is busy")
        self.expired_digests = expired_digests


@contextmanager
def maintenance_transaction(timeout_ms: int) -> Iterator[None]:
    """Timeouts are transaction-local, never changes to the web connection config."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [str(timeout_ms)])
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [str(min(timeout_ms, 5000))])
        yield


def _try_lock() -> bool:
    from core.mantecato_core.visitor_counting import _ROLLUP_LOCK_KEY

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [_ROLLUP_LOCK_KEY])
        return cursor.fetchone()[0]


def _units(now, website_id=None, period=None, finished_keys=None):
    from apps.core.models import VisitorDayState, VisitorScopeState
    from core.mantecato_core.visitor_counting import _period_ended, utc_day

    month_start = utc_day(now).replace(day=1)
    queries = []
    for model in (VisitorDayState, VisitorScopeState):
        qs = model.objects.all()
        if website_id:
            qs = qs.filter(website_id=website_id)
        if period:
            qs = qs.filter(period=period)
        if finished_keys is not None:
            qs = qs.filter(period__in=finished_keys)
        queries.append(qs.values_list("website_id", "period"))
    pairs = queries[0].union(queries[1])
    return sorted(
        ((str(site), key) for site, key in pairs if _period_ended(key, month_start)),
        key=lambda pair: (pair[1], pair[0]),
    )


def _insert_aggregates(table: str, key_column: str, select: str, params: list) -> None:
    # Only internal table/column names reach this builder. All data is parameterized.
    counters = ", ".join(_COUNTERS)
    bot_columns = ", ".join(f"bot_{name}" for name in _COUNTERS)
    updates = ", ".join(f"{name} = {table}.{name} + EXCLUDED.{name}" for name in _COUNTERS)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""INSERT INTO {table}
              (id, website_id, {key_column}, scope, scope_value, {counters},
               {bot_columns}, created_at, updated_at)
            SELECT gen_random_uuid(), website_id, key_date, scope, scope_value,
                   {counters}, 0, 0, 0, 0, 0, now(), now()
            FROM ({select}) aggregated
            ON CONFLICT (website_id, {key_column}, scope, scope_value)
            DO UPDATE SET {updates}, updated_at = now()""",
            params,
        )


def _rollup_unit(site: str, period: str, result: dict) -> None:
    from core.mantecato_core.visitor_counting import (
        _bounce_threshold,
        _first_day_of_period,
    )

    # Preserve daily/weekly legacy keys and their month-aligned output semantics.
    p_start = _first_day_of_period(period, "month").replace(day=1)
    threshold = _bounce_threshold()
    bounce = """cur_visit_pageviews <= 1 AND
      (%s <= 0 OR cur_visit_duration_s + cur_page_engaged_s < %s)"""
    sums = f"""COUNT(DISTINCT visitor_key)::integer AS unique_visitors,
      SUM(visits)::integer AS visits,
      (SUM(bounces) + COUNT(*) FILTER (WHERE {bounce}))::integer AS bounces,
      SUM(total_pageviews)::integer AS total_pageviews,
      SUM(total_duration_s + cur_visit_duration_s + cur_page_engaged_s)::integer
        AS total_duration_s"""
    where = "WHERE website_id = %s::uuid AND period = %s"
    params = [threshold, threshold, site, period]
    _insert_aggregates(
        "visitor_daily",
        "day",
        f"""SELECT website_id, day AS key_date, 'site' AS scope, '' AS scope_value,
            {sums} FROM visitor_day_state {where} GROUP BY website_id, day""",
        params,
    )
    _insert_aggregates(
        "visitor_period",
        "period_start",
        f"""SELECT website_id, date_trunc('month', MIN(day))::date AS key_date,
            'site' AS scope, '' AS scope_value,
            {sums} FROM visitor_day_state {where} GROUP BY website_id""",
        params,
    )
    _insert_aggregates(
        "visitor_period",
        "period_start",
        f"""SELECT website_id, key_date, 'landing' AS scope, scope_value,
          0 AS unique_visitors, SUM(visits)::integer AS visits,
          SUM(bounces)::integer AS bounces, 0 AS total_pageviews, 0 AS total_duration_s
          FROM (
            SELECT website_id, date_trunc('month', MIN(day))::date AS key_date,
              COALESCE(NULLIF(entry_path, ''), '/') AS scope_value,
              COUNT(*)::integer AS visits,
              COUNT(*) FILTER (WHERE {bounce})::integer AS bounces
            FROM visitor_day_state {where} AND entry_path IS NOT NULL
            GROUP BY website_id, entry_path
          ) paths GROUP BY website_id, key_date, scope_value""",
        params,
    )
    _insert_aggregates(
        "visitor_period",
        "period_start",
        f"""SELECT website_id, %s::date AS key_date, scope, scope_value,
          COUNT(DISTINCT visitor_key)::integer AS unique_visitors,
          0 AS visits, 0 AS bounces, 0 AS total_pageviews, 0 AS total_duration_s
          FROM visitor_scope_state {where} GROUP BY website_id, scope, scope_value""",
        [p_start, site, period],
    )
    # These tables have no dependent rows; avoid ORM collector/materialization.
    with connection.cursor() as cursor:
        for table, key in (("visitor_scope_state", "scope_rows"), ("visitor_day_state", "rows")):
            cursor.execute(f"DELETE FROM {table} {where}", [site, period])
            result[key] += cursor.rowcount


def _cleanup_salts(now, period=None) -> int:
    from apps.core.models import VisitorSalt
    from core.mantecato_core.visitor_counting import _period_ended, utc_day

    month_start = utc_day(now).replace(day=1)
    salts = VisitorSalt.objects.all()
    if period:
        salts = salts.filter(period=period)
    expired = [
        key for key in salts.values_list("period", flat=True) if _period_ended(key, month_start)
    ]
    if not expired:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            """DELETE FROM visitor_salt salt WHERE period = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM visitor_day_state d WHERE d.period = salt.period)
          AND NOT EXISTS (SELECT 1 FROM visitor_scope_state s WHERE s.period = salt.period)""",
            [expired],
        )
        return cursor.rowcount


def expire_digests(
    now=None, *, website_id=None, batch_size=5000, deadline=None, timeout_ms=60000
) -> int:
    """Bounded retention writes independent of monthly aggregation success."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    cutoff = (now or timezone.now()) - timedelta(days=settings.VISITOR_KEY_RETENTION_DAYS)
    total = 0
    while deadline is None or time.monotonic() < deadline:
        remaining_ms = (
            timeout_ms
            if deadline is None
            else min(timeout_ms, max(1, int((deadline - time.monotonic()) * 1000)))
        )
        with maintenance_transaction(remaining_ms), connection.cursor() as cursor:
            # Backfill reads these digests under the same lock. Retention commits
            # independently of aggregation, but must never erase its inputs.
            if not _try_lock():
                raise MaintenanceBusy(total)
            site_clause = "AND website_id = %s::uuid" if website_id else ""
            params = [cutoff, *([website_id] if website_id else []), batch_size]
            cursor.execute(
                f"""WITH expired AS (
              SELECT event_id FROM website_event
              WHERE created_at < %s AND visitor_key IS NOT NULL {site_clause}
              ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED
            ) UPDATE website_event e SET visitor_key = NULL FROM expired x
              WHERE e.event_id = x.event_id""",
                params,
            )
            count = cursor.rowcount
            total += count
        if count < batch_size:
            break
    return total


def run_rollup(
    now: datetime | None = None,
    *,
    finished_keys=None,
    website_id=None,
    period=None,
    dry_run=False,
    max_runtime=900.0,
    timeout_ms=60000,
) -> dict:
    """One bounded invocation; concurrent maintenance reports busy immediately."""
    if not isfinite(max_runtime) or max_runtime <= 0 or timeout_ms <= 0:
        raise ValueError("Runtime must be finite and positive; SQL timeout must be positive")
    now = now or timezone.now()
    started = time.monotonic()
    deadline = started + max_runtime
    result = {
        "periods": 0,
        "rows": 0,
        "salts": 0,
        "scope_rows": 0,
        "expired_digests": 0,
        "remaining_units": 0,
        "status": "completed",
    }
    from apps.core.models import WebsiteEvent

    def bounded_timeout():
        return min(timeout_ms, max(1, int((deadline - time.monotonic()) * 1000)))

    with maintenance_transaction(bounded_timeout()):
        units = _units(now, website_id, period, finished_keys)
    if dry_run:
        result.update(status="dry_run", remaining_units=len(units))
    else:
        # Retention is deliberately run even when there is no finished month.
        try:
            result["expired_digests"] = expire_digests(
                now, website_id=website_id, deadline=deadline, timeout_ms=bounded_timeout()
            )
        except MaintenanceBusy as exc:
            result.update(status="busy", expired_digests=exc.expired_digests)
        for site, key in units:
            if result["status"] != "completed":
                break
            if time.monotonic() >= deadline:
                result["status"] = "budget_exhausted"
                break
            with maintenance_transaction(bounded_timeout()):
                if not _try_lock():
                    result["status"] = "busy"
                    break
                # Recheck the selected source under the shared import/rollup lock.
                live = _units(now, site, key, finished_keys)
                if not live:
                    continue
                unit_result = {"rows": 0, "scope_rows": 0}
                _rollup_unit(site, key, unit_result)
                removed_salts = _cleanup_salts(now, key)
            # Only committed units are reported as successful.
            result["periods"] += 1
            result["rows"] += unit_result["rows"]
            result["scope_rows"] += unit_result["scope_rows"]
            result["salts"] += removed_salts
            logger.info("visitor_rollup unit_completed site=%s period=%s", site, key)
        if result["status"] == "completed" and time.monotonic() >= deadline:
            result["status"] = "budget_exhausted"
        if result["status"] == "completed":
            with maintenance_transaction(bounded_timeout()):
                if _try_lock():
                    result["salts"] += _cleanup_salts(now, period)
                else:
                    result["status"] = "busy"
        with maintenance_transaction(min(timeout_ms, 5000)):
            result["remaining_units"] = len(_units(now, website_id, period, finished_keys))
    # Short, separately bounded diagnostics can run after the unit runtime budget.
    # A skipped/locked retention row must not be mistaken for complete maintenance.
    with maintenance_transaction(min(timeout_ms, 5000)):
        expired = WebsiteEvent.objects.filter(
            created_at__lt=now - timedelta(days=settings.VISITOR_KEY_RETENTION_DAYS),
            visitor_key__isnull=False,
        )
        if website_id:
            expired = expired.filter(website_id=website_id)
        result["retention_pending"] = expired.exists()
    if result["status"] == "completed" and (
        result["remaining_units"] or result["retention_pending"]
    ):
        result["status"] = "budget_exhausted"
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result
