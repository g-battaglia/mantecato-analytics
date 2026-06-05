"""Management command to create a Mantecato user account.

Usage::

    python manage.py createuser admin --role admin
    python manage.py createuser alice --password secret123
    python manage.py createuser bob              # prompts for password
"""

from __future__ import annotations

import getpass

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import MantecatoUser


class Command(BaseCommand):
    """Create a new :class:`~apps.core.models.MantecatoUser`.

    The password is hashed via Django's ``set_password`` before storage.
    When ``--password`` is omitted the command prompts interactively with
    confirmation, mirroring the UX of ``createsuperuser``.
    """

    help = "Create a Mantecato user account."

    def add_arguments(self, parser):
        """Register the ``username``, ``--role``, and ``--password`` arguments.

        Args:
            parser: The :class:`~argparse.ArgumentParser` to configure.
        """
        parser.add_argument("username", help="Username for the new account.")
        parser.add_argument(
            "--role",
            choices=["user", "admin"],
            default="user",
            help="User role (default: user).",
        )
        parser.add_argument(
            "--password",
            help="Password (will prompt interactively if omitted).",
        )

    def handle(self, *args, **options):
        """Validate inputs and create the user.

        Raises:
            CommandError: On empty username, duplicate username, password
                mismatch, or password shorter than 4 characters.
        """
        username: str = options["username"].strip()
        role: str = options["role"]
        password: str | None = options["password"]

        if not username:
            raise CommandError("Username cannot be empty.")

        # Check for active (non-deleted) users with the same username.
        if MantecatoUser.objects.filter(username=username, deleted_at__isnull=True).exists():
            raise CommandError(f"User '{username}' already exists.")

        if not password:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Password (again): ")
            if password != confirm:
                raise CommandError("Passwords do not match.")

        if len(password) < 4:
            raise CommandError("Password must be at least 4 characters.")

        MantecatoUser.objects.create_user(username=username, password=password, role=role)
        self.stdout.write(self.style.SUCCESS(f"User '{username}' created (role={role})."))
