"""Run an optional Umami import using environment variables.

This command is intended for deployment hooks. It is a no-op unless
``UMAMI_IMPORT_ON_DEPLOY`` is enabled, so a public Blueprint can include it
without forcing every deployment to configure an Umami source database.
"""

from __future__ import annotations

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


def _env_bool(name: str, default: bool = False) -> bool:
    """Return a strict boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise CommandError(f"{name} must be true or false.")


class Command(BaseCommand):
    """Dispatch a deployment-time Umami import from environment variables."""

    help = "Run the Umami import configured by UMAMI_IMPORT_* environment variables."

    def handle(self, *args, **options):
        """Run the requested import mode, or exit successfully when disabled."""
        if not _env_bool("UMAMI_IMPORT_ON_DEPLOY"):
            self.stdout.write("Umami deploy import disabled.")
            return

        source_db = os.environ.get("UMAMI_DATABASE_URL", "").strip()
        if not source_db:
            raise CommandError(
                "UMAMI_DATABASE_URL is required when UMAMI_IMPORT_ON_DEPLOY=True."
            )

        mode = os.environ.get("UMAMI_IMPORT_MODE", "data").strip().lower()
        since = os.environ.get("UMAMI_IMPORT_SINCE") or None

        if mode == "data":
            call_command(
                "importumamidata",
                source_db=source_db,
                source_website=os.environ.get("UMAMI_SOURCE_WEBSITE_ID") or None,
                target_website=os.environ.get("MANTECATO_TARGET_WEBSITE_ID") or None,
                since=since,
                noinput=True,
            )
            return

        if mode == "full":
            if not _env_bool("UMAMI_IMPORT_ALLOW_CONFIG"):
                raise CommandError(
                    "UMAMI_IMPORT_ALLOW_CONFIG=True is required for a full import."
                )
            call_command(
                "importumami",
                source_db=source_db,
                include_config=True,
                confirm_replace_config=True,
                noinput=True,
                since=since,
            )
            return

        raise CommandError("UMAMI_IMPORT_MODE must be 'data' or 'full'.")
