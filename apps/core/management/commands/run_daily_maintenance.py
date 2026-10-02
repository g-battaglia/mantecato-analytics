"""Independent budgets and outcomes: never let rollup skip AI retention."""

import json
import math

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.ai_connections.maintenance import cleanup
from core.mantecato_core.visitor_counting import rollup_finished_periods


class Command(BaseCommand):
    help = "Run visitor maintenance and AI cleanup independently; no web server or imports."

    def add_arguments(self, parser):
        parser.add_argument("--rollup-runtime", type=float, default=900)
        parser.add_argument("--ai-runtime", type=float, default=120)
        parser.add_argument("--sql-timeout-ms", type=int, default=60000)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if (
            any(
                not math.isfinite(options[k]) or options[k] <= 0
                for k in ("rollup_runtime", "ai_runtime")
            )
            or options["sql_timeout_ms"] <= 0
        ):
            raise CommandError("Budgets must be finite and positive")
        outcomes = {}
        jobs = [
            (
                "visitors",
                lambda: rollup_finished_periods(
                    max_runtime=options["rollup_runtime"],
                    timeout_ms=options["sql_timeout_ms"],
                    dry_run=options["dry_run"],
                ),
            ),
            (
                "ai",
                lambda: cleanup(
                    max_runtime=options["ai_runtime"],
                    timeout_ms=min(options["sql_timeout_ms"], 5000),
                    dry_run=options["dry_run"],
                ),
            ),
        ]
        for name, job in jobs:
            try:
                outcomes[name] = job()
            except Exception as exc:
                outcomes[name] = {"status": "error", "error_type": type(exc).__name__}
            finally:
                connections.close_all()
        self.stdout.write(json.dumps(outcomes, sort_keys=True))
        statuses = [outcome["status"] for outcome in outcomes.values()]
        if "error" in statuses:
            raise CommandError("One or more maintenance jobs failed", returncode=1)
        if any(status not in ("completed", "dry_run") for status in statuses):
            raise CommandError("Maintenance incomplete", returncode=2)
