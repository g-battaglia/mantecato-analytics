import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.ai_connections.maintenance import cleanup


class Command(BaseCommand):
    help = "Offline batched cleanup of expired AI credentials and metadata-only audit."

    def add_arguments(self, parser):
        parser.add_argument("--max-runtime", type=float, default=120)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--sql-timeout-ms", type=int, default=5000)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            result = cleanup(
                max_runtime=options["max_runtime"],
                batch_size=options["batch_size"],
                timeout_ms=options["sql_timeout_ms"],
                dry_run=options["dry_run"],
            )
            self.stdout.write(json.dumps(result, sort_keys=True))
            if result["status"] not in ("completed", "dry_run"):
                raise CommandError("AI cleanup incomplete: " + result["status"], returncode=2)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError("AI cleanup failed: " + type(exc).__name__) from None
        finally:
            connections.close_all()
