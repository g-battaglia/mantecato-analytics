"""Compare the former Python sets with SQL DISTINCT on synthetic local data.

Requires empty analytics tables in a dedicated test_* or *_test PostgreSQL DB.
Each strategy runs in a fresh interpreter. Output includes sampled process/DB
memory, but RSS sums double-count shared pages; use Linux PSS/cgroups for budgets.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mantecato.settings")

import django

django.setup()

from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.core.models import WebsiteEvent  # noqa: E402
from core.mantecato_core.queries.stats import _normalize_url  # noqa: E402
from core.mantecato_core.scope_reads import (  # noqa: E402
    _decimal_digit_pattern,
    section_uniques,
)
from core.mantecato_core.visitor_counting import section_for_path  # noqa: E402
from mantecato.memory import MemorySampler  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visitors", type=int, default=100_000)
    parser.add_argument("--database-pid", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=["reference", "sql"], help=argparse.SUPPRESS)
    parser.add_argument("--site", type=uuid.UUID, help=argparse.SUPPRESS)
    args = parser.parse_args()
    db = connection.settings_dict
    host = db.get("OPTIONS", {}).get("host") or db.get("HOST", "")
    if not (
        host in ("localhost", "127.0.0.1") or (host.startswith("/") and Path(host).is_dir())
    ) or not (db["NAME"].startswith("test_") or db["NAME"].endswith("_test")):
        parser.error("Explicit local test PostgreSQL required; remote/production is forbidden")
    if not 1 <= args.visitors <= 1_000_000 or (
        args.database_pid is not None and args.database_pid < 1
    ):
        parser.error("Use 1–1000000 visitors and a positive database PID")
    if args.child:
        if args.site is None:
            parser.error("Internal child requires a synthetic site UUID")
        run_child(args)
        return
    # Refuse to add fixtures to an environment that already has analytics data.
    with connection.cursor() as cursor:
        for table in (
            "website_event",
            "visitor_day_state",
            "visitor_scope_state",
            "visitor_daily",
            "visitor_period",
        ):
            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {table})")
            if cursor.fetchone()[0]:
                parser.error("Empty isolated analytics tables required")
    site = uuid.uuid4()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO website_event
                (event_id, website_id, created_at, url_path, event_type, visitor_key)
                SELECT gen_random_uuid(), %s::uuid, now(),
                  '/article/' || i::text || '/' || duplicate::text, 1,
                  md5(i::text) || md5(i::text)
                FROM generate_series(1, %s) i CROSS JOIN generate_series(1, 2) duplicate""",
                [str(site), args.visitors],
            )
        result = {"visitors": args.visitors, "events": args.visitors * 2}
        for strategy in ("reference", "sql"):
            command = [sys.executable, __file__, "--child", strategy, "--site", str(site)]
            if args.database_pid:
                command.extend(["--database-pid", str(args.database_pid)])
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            result[strategy] = json.loads(completed.stdout)
        assert (
            result["reference"]["counts"]
            == result["sql"]["counts"]
            == {"/article/:id": args.visitors}
        )
        rendered = json.dumps(result, indent=2)
        if args.output:
            args.output.write_text(rendered + "\n")
        print(rendered)
    finally:
        WebsiteEvent.objects.filter(website_id=site).delete()
        connection.close()


def run_child(args):
    now = timezone.now()
    qs = WebsiteEvent.objects.filter(
        website_id=args.site,
        event_type=1,
        visitor_key__isnull=False,
        created_at__range=(now - timedelta(days=1), now),
    )
    # Exclude one-time normalizer setup from the warm query comparison.
    _decimal_digit_pattern()
    roots = (os.getpid(),) + ((args.database_pid,) if args.database_pid else ())
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SET LOCAL work_mem = '1MB'")
        cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        started = time.perf_counter()
        with MemorySampler(lambda: roots, interval=0.1) as memory:
            if args.child == "sql":
                counts = section_uniques(qs, ["/article/:id"])
            else:
                seen = defaultdict(set)
                for path, key in qs.values_list("url_path", "visitor_key").iterator():
                    section = _normalize_url(section_for_path(path), "smart")
                    if section == "/article/:id":
                        seen[section].add(key)
                counts = {section: len(keys) for section, keys in seen.items()}
                # Keep the reference sets alive through the final sample, as
                # they were during the former per-request computation.
        result = {
            "counts": counts,
            "wall_ms": round((time.perf_counter() - started) * 1000, 1),
            "memory": memory.result,
            "process_lifetime_peak_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    connection.close()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
