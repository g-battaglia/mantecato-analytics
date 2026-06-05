"""DATA-ONLY import from Umami — analytics rows only, never configuration.

Copies sessions, events, event data, session data and revenue. It never writes
to the configuration tables (users, teams, websites, segments, reports), so it
is safe to run against a live Mantecato instance without affecting login or
event tracking.

Single-site mode imports one Umami website and remaps its ``website_id`` onto an
**existing** Mantecato website, so historical analytics land under a site you
already track (and already have a tracker installed for).

Usage:
    # every website, keeping each website_id as-is
    python manage.py importumamidata --source-db "postgresql://..."

    # single site: import the Umami website <src> under existing Mantecato site <dst>
    python manage.py importumamidata --source-db "..." \
        --source-website <umami-uuid> --target-website <mantecato-uuid>

    # overwrite (delete the target site's existing analytics rows first)
    python manage.py importumamidata --source-db "..." \
        --source-website <umami-uuid> --target-website <mantecato-uuid> --replace
"""

from __future__ import annotations

import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from rich.console import Console
from rich.progress import Progress

from apps.core.services import UmamiImporter


class Command(BaseCommand):
    """Import only analytics data from Umami, optionally for a single website."""

    help = "Import ONLY analytics data from Umami (never config). Supports single-site remap."

    def add_arguments(self, parser):
        """Register the source DSN, the single-site remap options and filters."""
        parser.add_argument(
            "--source-db",
            default=os.environ.get("UMAMI_DATABASE_URL"),
            help=(
                "PostgreSQL connection string for the source Umami database. "
                "Defaults to UMAMI_DATABASE_URL."
            ),
        )
        parser.add_argument(
            "--source-website",
            default=os.environ.get("UMAMI_SOURCE_WEBSITE_ID"),
            help=(
                "Umami website_id (UUID) to import. Requires --target-website. "
                "Defaults to UMAMI_SOURCE_WEBSITE_ID."
            ),
        )
        parser.add_argument(
            "--target-website",
            default=os.environ.get("MANTECATO_TARGET_WEBSITE_ID"),
            help=(
                "Existing Mantecato website_id (UUID) to map imported rows onto. "
                "Defaults to MANTECATO_TARGET_WEBSITE_ID."
            ),
        )
        parser.add_argument(
            "--since",
            default=os.environ.get("UMAMI_IMPORT_SINCE"),
            help=(
                "Import only analytics rows after this date (YYYY-MM-DD). "
                "Defaults to UMAMI_IMPORT_SINCE."
            ),
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete the target website's existing analytics rows first "
            "(single-site only). Off by default — the import is additive.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Run non-interactively (skip the --replace confirmation).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show source row counts without importing.",
        )

    def handle(self, *args, **options):
        """Validate the single-site options, then run the analytics-only import.

        Raises:
            CommandError: On inconsistent website flags, invalid UUID/date, a
                failed --replace confirmation, or an unreachable source DB.
        """
        console = Console()
        source_db = options["source_db"]
        source_website = options["source_website"]
        target_website = options["target_website"]

        if not source_db:
            raise CommandError("Provide --source-db or set UMAMI_DATABASE_URL.")
        if bool(source_website) != bool(target_website):
            raise CommandError(
                "--source-website and --target-website must be used together."
            )
        if options["replace"] and not target_website:
            raise CommandError(
                "--replace is only valid in single-site mode "
                "(--source-website/--target-website)."
            )

        since_date = self._parse_since(options["since"])

        try:
            importer = UmamiImporter(
                source_db,
                console,
                data_only=True,
                since_date=since_date,
                source_website=source_website,
                target_website=target_website,
            )
        except ValueError as exc:  # invalid UUID
            raise CommandError(str(exc)) from exc

        try:
            src = importer.connect()
        except ConnectionError as exc:
            raise CommandError(str(exc)) from exc

        try:
            console.print("\n[bold]Source analytics row counts:[/bold]")
            for label, count in importer.source_counts(src).items():
                console.print(f"  {label}: {count}")

            if options["dry_run"]:
                console.print("\n[yellow]Dry run — no data imported.[/yellow]")
                return

            if target_website:
                console.print(
                    f"\n[bold]Remapping Umami website {source_website} "
                    f"→ Mantecato website {target_website}[/bold]"
                )

            if options["replace"]:
                self._confirm_replace(console, options, target_website)
                console.print(
                    "[yellow]Deleting existing analytics rows for the target website…[/yellow]"
                )
                importer.replace_target_data()

            with Progress(console=console) as progress:
                importer.run(src, progress)
            console.print("\n[bold green]Data-only import complete.[/bold green]")
        finally:
            src.close()

    @staticmethod
    def _parse_since(since):
        """Parse the optional ``--since`` date, raising on a bad format."""
        if not since:
            return None
        try:
            return datetime.strptime(since, "%Y-%m-%d")
        except ValueError as exc:
            raise CommandError("Invalid date format. Use YYYY-MM-DD.") from exc

    @staticmethod
    def _confirm_replace(console, options, target_website):
        """Require explicit confirmation before deleting the target site's rows.

        Raises:
            CommandError: If the interactive confirmation is not satisfied.
        """
        if options["noinput"]:
            return
        console.print(
            f"[bold red]--replace will DELETE existing analytics rows for website "
            f"{target_website}.[/bold red]"
        )
        if input("Type 'REPLACE' to continue: ").strip() != "REPLACE":
            raise CommandError("Confirmation failed. Aborted.")
