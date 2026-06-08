"""Finalise and discard past-day visitor state (the compute-and-discard rollup).

Run this once a day (e.g. a platform Cron Job / system cron) for the strict
"pseudonymous data lives at most ~24h" guarantee. It is idempotent and also runs
opportunistically when the dashboard is opened, so a missed run self-heals.

    python manage.py rollup_visitors
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from core.mantecato_core.visitor_counting import rollup_finished_days


class Command(BaseCommand):
    """Aggregate finished days into ``visitor_daily`` and delete the ephemeral
    per-visitor state + that day's salt."""

    help = "Roll up and discard past-day visitor state into permanent daily aggregates."

    def handle(self, *args: Any, **options: Any) -> None:
        result = rollup_finished_days()
        self.stdout.write(
            self.style.SUCCESS(
                f"Rolled up {result['days']} site-day(s); "
                f"discarded {result['rows']} state row(s) and {result['salts']} salt(s)."
            )
        )
