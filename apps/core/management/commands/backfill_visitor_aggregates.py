"""Backfill permanent visitor aggregates from per-event digests.

Sessionises ``website_event.visitor_key`` (e.g. set by the Umami import from
``session_id``) into the permanent ``VisitorDaily``/``VisitorPeriod`` aggregates
for days that have no live state, then discards the digests. Idempotent — safe to
re-run; processed rows are skipped.

    python manage.py backfill_visitor_aggregates [--website <uuid>]
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from core.mantecato_core.visitor_counting import aggregate_events_into_daily


class Command(BaseCommand):
    help = "Aggregate imported per-event visitor digests into the permanent visitor aggregates."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--website", default=None, help="Limit to one website UUID.")

    def handle(self, *args: Any, **options: Any) -> None:
        result = aggregate_events_into_daily(options.get("website"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfilled {result['days']} site-day(s); discarded {result['events']} digest(s)."
            )
        )
