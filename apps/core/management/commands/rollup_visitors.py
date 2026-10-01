"""Daily offline retention and finished-month rollup; never part of web startup."""

from __future__ import annotations

import json
import logging
import uuid
from math import isfinite
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.mantecato_core.visitor_counting import (
    _period_bounds_of_key,
    rollup_finished_periods,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Offline retention and atomic rollup of finished visitor windows."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--website", type=uuid.UUID)
        parser.add_argument("--period", help="Finished YYYY-MM, legacy YYYY-MM-DD or YYYY-Www")
        parser.add_argument("--dry-run", action="store_true", help="Inspect backlog without writes")
        parser.add_argument("--max-runtime", type=float, default=900, help="Budget in seconds")
        parser.add_argument("--sql-timeout-ms", type=int, default=60000)

    def handle(self, *args: Any, **options: Any) -> None:
        if (
            not isfinite(options["max_runtime"])
            or options["max_runtime"] <= 0
            or options["sql_timeout_ms"] <= 0
        ):
            raise CommandError("Runtime must be finite and positive; SQL timeout must be positive")
        period = options.get("period")
        if period:
            try:
                _period_bounds_of_key(period)
            except (ValueError, TypeError) as exc:
                raise CommandError("Invalid period key") from exc
        logger.info("visitor_rollup started dry_run=%s", options["dry_run"])
        try:
            result = rollup_finished_periods(
                website_id=options.get("website"),
                period=period,
                dry_run=options["dry_run"],
                max_runtime=options["max_runtime"],
                timeout_ms=options["sql_timeout_ms"],
            )
            summary = json.dumps(result, sort_keys=True)
            self.stdout.write(summary)
            logger.info("visitor_rollup finished %s", summary)
            if result["status"] not in ("completed", "dry_run"):
                raise CommandError(f"Maintenance incomplete: {result['status']}", returncode=2)
        except CommandError:
            raise
        except Exception as exc:
            # SQL exceptions may include values. Log a type, never SQL or digests.
            logger.error("visitor_rollup failed error_type=%s", type(exc).__name__)
            raise CommandError(f"Maintenance failed: {type(exc).__name__}") from exc
        finally:
            connections.close_all()
