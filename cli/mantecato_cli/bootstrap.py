"""Django bootstrap for CLI — call setup_django() before any ORM or service calls."""

from __future__ import annotations

import contextlib
import os
import sys


def setup_django() -> None:
    """Configure Django settings and call django.setup() if not already done.

    Safe to call multiple times — idempotent after the first invocation.
    """
    if "django" not in sys.modules or not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mantecato.settings")

    import django

    with contextlib.suppress(RuntimeError):
        django.setup()
