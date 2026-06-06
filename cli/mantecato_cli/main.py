"""Mantecato CLI entry point.

Thin shim: wires the Typer ``app`` (defined in ``app.py``) to the command
modules under ``commands/``. The ``setup_django`` re-export keeps the existing
test patches (``@patch("cli.mantecato_cli.main.setup_django")``) working.
"""

from __future__ import annotations

from cli.mantecato_cli.app import app
from cli.mantecato_cli.bootstrap import setup_django  # noqa: F401

# Importing these modules registers their @app.command decorators on `app`.
# Order matters: it determines the order of commands in `mantecato --help`.
# isort: off
from cli.mantecato_cli.commands import analytics  # noqa: F401
from cli.mantecato_cli.commands import queries  # noqa: F401
from cli.mantecato_cli.commands import crud  # noqa: F401
# isort: on

__all__ = ["app", "setup_django"]
