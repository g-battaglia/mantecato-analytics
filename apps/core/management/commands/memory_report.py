"""Read-only process/cgroup memory report; no database access by default."""

import json
import math
import os
import time

from django.core.management.base import BaseCommand, CommandError

from mantecato.memory import snapshot


class Command(BaseCommand):
    help = "Report memory as JSON lines without exporting commands, environment or analytics."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--pid", type=int, action="append", help="Root PID (repeatable).")
        parser.add_argument("--samples", type=int, default=1)
        parser.add_argument("--interval", type=float, default=0.25)
        parser.add_argument("--database", action="store_true", help="Include bounded DB metadata.")

    def handle(self, *args, **options):
        if (
            not 1 <= options["samples"] <= 3600
            or not math.isfinite(options["interval"])
            or options["interval"] < 0.1
        ):
            raise CommandError("Use 1–3600 samples and an interval of at least 0.1 seconds.")
        roots = tuple(options["pid"] or [os.getpid()])
        if any(pid < 1 for pid in roots):
            raise CommandError("PIDs must be positive.")
        database = self.database_metadata() if options["database"] else None
        for index in range(options["samples"]):
            if index:
                time.sleep(options["interval"])
            result = snapshot(roots)
            result["sample"] = index
            if database is not None:
                result["database"] = database
            self.stdout.write(json.dumps(result))

    def database_metadata(self):
        """No SQL text, query parameters, identities or visitor data are read."""
        from django.db import connection, transaction

        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SET LOCAL lock_timeout = '250ms'")
                cursor.execute("""SELECT name, setting, unit FROM pg_settings WHERE name IN (
                    'shared_buffers', 'work_mem', 'hash_mem_multiplier',
                    'maintenance_work_mem', 'autovacuum_work_mem',
                    'max_connections', 'max_parallel_workers_per_gather',
                    'autovacuum_max_workers') ORDER BY name""")
                settings = [
                    dict(zip(("name", "setting", "unit"), row, strict=True))
                    for row in cursor.fetchall()
                ]
                cursor.execute("""SELECT count(*), count(*) FILTER (WHERE state = 'active')
                    FROM pg_stat_activity WHERE datname = current_database()""")
                total, active = cursor.fetchone()
                cursor.execute("""SELECT temp_files, temp_bytes, deadlocks FROM pg_stat_database
                    WHERE datname = current_database()""")
                counters = cursor.fetchone()
                return {
                    "settings": settings,
                    "backends": total,
                    "active_backends": active,
                    "temp_files": counters[0],
                    "temp_bytes": counters[1],
                    "deadlocks": counters[2],
                    "note": "Counters are cumulative; this observer is included in backends.",
                }
        finally:
            connection.close()
