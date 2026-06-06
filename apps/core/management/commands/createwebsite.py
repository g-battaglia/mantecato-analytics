"""Management command to create a tracked website.

Usage::

    python manage.py createwebsite --name "My Site" --domain "example.com"
    python manage.py createwebsite --name "Blog" --user-id <uuid>
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Website


class Command(BaseCommand):
    """Create a new :class:`~apps.core.models.Website` for event tracking.

    The generated UUID is printed on success and can be passed to the JS
    tracker's ``data-website-id`` attribute.
    """

    help = "Create a tracked website."

    def add_arguments(self, parser):
        """Register ``--name``, ``--domain``, ``--user-id``, ``--team-id`` arguments.

        Args:
            parser: The :class:`~argparse.ArgumentParser` to configure.
        """
        parser.add_argument("--name", required=True, help="Display name for the website.")
        parser.add_argument("--domain", default=None, help="Domain (e.g. example.com).")
        parser.add_argument("--user-id", default=None, help="Owner user UUID (optional).")
        parser.add_argument("--team-id", default=None, help="Owner team UUID (optional).")

    def handle(self, *args, **options):
        """Validate the name and create the website row.

        Raises:
            CommandError: If the ``--name`` value is empty after stripping.
        """
        name: str = options["name"].strip()
        if not name:
            raise CommandError("Name cannot be empty.")

        site = Website.objects.create(
            name=name,
            domain=options["domain"],
            user_id=options["user_id"],
            team_id=options["team_id"],
        )
        self.stdout.write(self.style.SUCCESS(f"Website '{name}' created (id={site.id})."))
