"""Synthetic local-only benchmark. Run after migrating an isolated PostgreSQL DB.

    uv run python tools/benchmark_analytics.py --visitors 1000 --output /tmp/baseline.json

Never uses remote databases or real traffic. Removes only its own random site's data.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mantecato.settings")

import django

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.analytics.services import get_overview_data, get_realtime_data  # noqa: E402
from apps.api.v1.contracts import parse_query  # noqa: E402
from apps.api.v1.services import run_query  # noqa: E402
from apps.core.models import (  # noqa: E402
    VisitorDaily,
    VisitorDayState,
    VisitorPeriod,
    VisitorScopeState,
    WebsiteEvent,
)
from apps.tracker.services import ingest_pageview  # noqa: E402
from core.mantecato_core.date_utils import DateRange  # noqa: E402
from core.mantecato_core.visitor_counting import (  # noqa: E402
    event_visitor_stats,
    record_engagement,
    rollup_finished_periods,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visitors", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    host = connection.settings_dict.get("OPTIONS", {}).get(
        "host", connection.settings_dict.get("HOST", "")
    )
    if host not in ("127.0.0.1", "localhost") and not (
        host.startswith("/") and Path(host).is_dir()
    ):
        parser.error("Use an explicitly configured loopback or local socket PostgreSQL DB")
    if args.visitors < 1:
        parser.error("--visitors must be positive")
    name = str(connection.settings_dict.get("NAME", ""))
    if not (name.startswith("test_") or name.endswith("_test")):
        parser.error("Use a dedicated test database named test_* or *_test")
    # Even the reference rollup/retention must not touch unrelated data.
    if any(
        model.objects.exists()
        for model in (
            WebsiteEvent,
            VisitorDayState,
            VisitorScopeState,
            VisitorDaily,
            VisitorPeriod,
        )
    ):
        parser.error("Benchmark needs empty isolated analytics tables")
    site = uuid.uuid4()
    now = timezone.now()
    end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = (end - timedelta(days=1)).replace(day=1)
    period = start.strftime("%Y-%m")
    results = {}

    def measure(name, action):
        queries = 0
        db_ms = 0.0

        def execute(execute, sql, params, many, context):
            nonlocal queries, db_ms
            before = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                queries += 1
                db_ms += (time.perf_counter() - before) * 1000

        usage_before = resource.getrusage(resource.RUSAGE_SELF)
        before = time.perf_counter()
        with connection.execute_wrapper(execute):
            action()
        usage_after = resource.getrusage(resource.RUSAGE_SELF)
        results[name] = {
            "process_cpu_ms": round(
                1000
                * (
                    usage_after.ru_utime
                    + usage_after.ru_stime
                    - usage_before.ru_utime
                    - usage_before.ru_stime
                ),
                2,
            ),
            "wall_ms": round((time.perf_counter() - before) * 1000, 2),
            "sql_ms": round(db_ms, 2),
            "queries": queries,
            "peak_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }

    try:
        VisitorDayState.objects.bulk_create(
            [
                VisitorDayState(
                    website_id=site,
                    day=start.date(),
                    period=period,
                    visitor_key=str(i),
                    first_seen=start,
                    last_seen=start + timedelta(seconds=20),
                    total_pageviews=2,
                    cur_visit_pageviews=2,
                    cur_visit_duration_s=20,
                    entry_path=f"/p/{i}",
                )
                for i in range(args.visitors)
            ]
        )
        VisitorScopeState.objects.bulk_create(
            [
                VisitorScopeState(
                    website_id=site,
                    period=period,
                    visitor_key=str(i),
                    scope=scope,
                    scope_value=value,
                )
                for i in range(args.visitors)
                for scope, value in [
                    ("page", f"/p/{i}"),
                    *[("group", f"tag:{g}/p/{i}") for g in range(12)],
                ]
            ]
        )
        WebsiteEvent.objects.bulk_create(
            [
                WebsiteEvent(website_id=site, url_path=f"/p/{i}", visitor_key=str(i))
                for i in range(args.visitors)
                for _ in range(2)
            ]
        )
        WebsiteEvent.objects.filter(website_id=site).update(created_at=start)
        common = {
            "website_id": str(site),
            "operation": "totals",
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        measure(
            "api_pageviews",
            lambda: run_query(
                parse_query(
                    {
                        **common,
                        "metrics": ["pageviews"],
                    }
                )
            ),
        )
        measure(
            "api_visits",
            lambda: run_query(
                parse_query(
                    {
                        **common,
                        "metrics": ["visits", "bounces", "daily_unique_visitors"],
                    }
                )
            ),
        )
        measure(
            "dashboard_sessions",
            lambda: event_visitor_stats(WebsiteEvent.objects.filter(website_id=site)),
        )
        for days in (1, 7, 30, 365):
            read_end = start + timedelta(days=1)
            window = DateRange(read_end - timedelta(days=days), read_end)
            measure(
                f"dashboard_{days}d",
                lambda window=window: get_overview_data(str(site), window, lazy_tabs=True),
            )
        measure("realtime_empty", lambda: get_realtime_data(str(site)))
        measure("rollup", rollup_finished_periods)
        measure(
            "ingest_100",
            lambda: [
                ingest_pageview(
                    str(site),
                    {"url": "/active"},
                    {},
                    None,
                    ip="127.0.0.1",
                    user_agent="Synthetic benchmark",
                )
                for _ in range(100)
            ],
        )
        measure(
            "engagement_100",
            lambda: [
                record_engagement(
                    website_id=str(site),
                    occurred_at=timezone.now(),
                    ip="127.0.0.1",
                    user_agent="Synthetic benchmark",
                    seconds=i,
                )
                for i in range(1, 101)
            ],
        )
        report = {
            "visitors": args.visitors,
            "scope_rows": args.visitors * 13,
            "postgres": connection.pg_version,
            "results": results,
            "notice": "Synthetic single-run local benchmark, not a production SLA",
        }
        print(json.dumps(report, indent=2))
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        for model in (
            WebsiteEvent,
            VisitorDayState,
            VisitorScopeState,
            VisitorDaily,
            VisitorPeriod,
        ):
            model.objects.filter(website_id=site).delete()


if __name__ == "__main__":
    main()
