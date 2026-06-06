"""FULL import from an Umami database into Mantecato — INCLUDING configuration.

This is the **destructive** variant. In addition to analytics rows it copies
*configuration*: users, teams, websites, segments and reports. Importing a
foreign ``website`` row (or otherwise replacing the existing configuration)
breaks event ingestion, because the tracker posts a **hardcoded** ``website_id``
that must keep matching a row in the ``website`` table.

For the safe, additive, analytics-only import use :mod:`importumamidata` instead.

Because of the blast radius, this command refuses to run unless
``--include-config`` is passed *and* the operator confirms interactively (or
passes ``--noinput --confirm-replace-config`` for automation).

Usage:
    python manage.py importumami --source-db "postgresql://..." --include-config
    python manage.py importumami --source-db "..." --include-config --dry-run
    python manage.py importumami --source-db "..." --include-config \
        --noinput --confirm-replace-config
"""

from __future__ import annotations

import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from rich.console import Console
from rich.progress import Progress

from apps.core.services import UmamiImporter


class Command(BaseCommand):
    """Run the full (configuration-inclusive) Umami import behind confirmations."""

    help = (
        "FULL Umami import INCLUDING configuration (destructive). "
        "Prefer 'importumamidata' for a safe analytics-only import."
    )

    def add_arguments(self, parser):
        """Register the source DSN, the safety flags and the optional filters."""
        parser.add_argument(
            "--source-db",
            default=os.environ.get("UMAMI_DATABASE_URL"),
            help=(
                "PostgreSQL connection string for the source Umami database. "
                "Defaults to UMAMI_DATABASE_URL."
            ),
        )
        parser.add_argument(
            "--include-config",
            action="store_true",
            help="Required acknowledgement: also import configuration "
            "(users/websites/reports). This can break tracking.",
        )
        parser.add_argument(
            "--confirm-replace-config",
            action="store_true",
            help="Bypass the interactive prompt (only valid together with --noinput).",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Run non-interactively (requires --confirm-replace-config).",
        )
        parser.add_argument(
            "--skip-events",
            action="store_true",
            help="Import only configuration, skip analytics data.",
        )
        parser.add_argument(
            "--since",
            default=None,
            help="Import only analytics rows after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show source row counts without importing.",
        )

    def handle(self, *args, **options):
        """Gate the full import behind --include-config and confirmations, then run it.

        Raises:
            CommandError: If the acknowledgement flag is missing, the
                confirmation fails, the date is malformed, or the source DB is
                unreachable.
        """
        console = Console()
        source_db = options["source_db"]

        if not options["include_config"]:
            raise CommandError(
                "Refusing to run: this is the FULL import and it overwrites Mantecato "
                "configuration (users, websites, reports), which can break event tracking.\n"
                "  • To import ONLY analytics data safely:  python manage.py importumamidata ...\n"
                "  • To really run the full import:         re-run with --include-config"
            )
        if not source_db:
            raise CommandError("Provide --source-db or set UMAMI_DATABASE_URL.")

        since_date = self._parse_since(options["since"])
        self._confirm(console, options)

        importer = UmamiImporter(
            source_db,
            console,
            data_only=False,
            since_date=since_date,
            skip_events=options["skip_events"],
        )
        try:
            src = importer.connect()
        except ConnectionError as exc:
            raise CommandError(str(exc)) from exc

        try:
            self._print_counts(console, importer.source_counts(src))
            if options["dry_run"]:
                console.print("\n[yellow]Dry run — no data imported.[/yellow]")
                return
            with Progress(console=console) as progress:
                importer.run(src, progress)
            console.print("\n[bold green]Full import complete.[/bold green]")
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
    def _confirm(console, options):
        """Show the destructive-action warning and require explicit confirmation.

        Interactive mode asks the operator to type the target database name and
        then the literal ``IMPORT CONFIG``. Non-interactive mode (``--noinput``)
        is only allowed together with ``--confirm-replace-config``.

        Raises:
            CommandError: If confirmation is not satisfied.
        """
        db = connection.settings_dict
        name = str(db.get("NAME"))
        target = f"{name} @ {db.get('HOST') or 'localhost'}"

        console.print(
            "\n[bold red]⚠  FULL IMPORT — this writes CONFIGURATION "
            "(users, websites, reports).[/bold red]"
        )
        console.print(f"[bold]Target database:[/bold] {target}")
        console.print(
            "[yellow]Importing a foreign 'website' row can break tracking "
            "(the tracker posts a hardcoded website_id).[/yellow]"
        )
        console.print(
            "[yellow]For analytics-only, non-destructive imports use "
            "'importumamidata' instead.[/yellow]\n"
        )

        if options["noinput"]:
            if not options["confirm_replace_config"]:
                raise CommandError(
                    "--noinput requires --confirm-replace-config for the full import."
                )
            return

        if input(f"Type the target database name ({name}) to continue: ").strip() != name:
            raise CommandError("Confirmation failed (database name mismatch). Aborted.")
        if input("Type 'IMPORT CONFIG' to confirm the full import: ").strip() != "IMPORT CONFIG":
            raise CommandError("Confirmation failed. Aborted.")

    @staticmethod
    def _print_counts(console, counts):
        """Print the per-table source row counts."""
        console.print("\n[bold]Source database row counts:[/bold]")
        for label, count in counts.items():
            console.print(f"  {label}: {count}")
