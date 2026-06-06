"""Typer app, shared CLI options, and command-level helpers.

The constants and helpers below are imported by every command module under
:mod:`cli.mantecato_cli.commands`. Centralising them removes the
``typer.Option(..., "--website", "-w")`` boilerplate that used to be
duplicated across 50+ commands and standardises the "fetch range, parse
filters, emit output" handshake.

Public surface:

- :data:`app`: the root :class:`typer.Typer` instance.
- :data:`FORMAT_OPTION`, :data:`WEBSITE_OPT`, :data:`RANGE_OPT`,
  :data:`USER_OPT`, :data:`FILTER_OPTION`: shared CLI option declarations.
- :func:`bootstrap`: ensure Django is configured before the first ORM call.
- :func:`resolve_range`: parse a date-range preset string to a ``DateRange``.
- :func:`parse_filters`: parse the repeated ``--filter`` arguments.
- :func:`emit`: render the result dict in the chosen output format.
- :func:`run_with_range`: standard "bootstrap + range + emit" wrapper used by
  every analytics command.
- :func:`get_or_die`: error-exit helper for the "object not found" branches
  that previously repeated 18+ times across the CRUD commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

from cli.mantecato_cli.helpers import format_output

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(
    name="mantecato",
    help="Mantecato analytics CLI — queries the Umami database directly.",
    no_args_is_help=True,
)

# Output format selector — accepted by every command that returns data.
FORMAT_OPTION = typer.Option("table", "--format", help="Output format: json, table, csv")

# Repeated ``--filter`` arguments parsed by ``core.mantecato_core.filters``.
FILTER_OPTION = typer.Option(None, "--filter")

# Shared option declarations used across analytics + CRUD commands. Typer
# treats these as templates: passing them as the default of a parameter
# is equivalent to declaring the option inline at the call site.
WEBSITE_OPT = typer.Option(..., "--website", "-w", help="Website UUID")
RANGE_OPT = typer.Option("30d", "--range", "-r", help="Date range preset (e.g. 7d, 30d, today)")
USER_OPT = typer.Option(..., "--user", "-u", help="User UUID")

# Aliased option variants used by the low-level query commands; the extra
# ``--site`` / ``--period`` flags preserve compatibility with the upstream
# Umami CLI vocabulary that some users still type.
WEBSITE_ALIAS_OPT = typer.Option(..., "--website", "-w", "--site", "-s", help="Website UUID")
RANGE_ALIAS_OPT = typer.Option(
    "30d", "--range", "-r", "--period", "-p", help="Date range preset"
)
LIMIT_OPT = typer.Option(20, "--limit", "-l", help="Maximum rows returned")


def bootstrap() -> None:
    """Ensure Django settings are loaded before the first ORM call.

    Lookup is deferred through :mod:`cli.mantecato_cli.main` so tests that
    ``@patch("cli.mantecato_cli.main.setup_django")`` still take effect.
    """
    from cli.mantecato_cli import main as _main

    _main.setup_django()


def resolve_range(preset: str):
    """Parse a date-range preset to a :class:`DateRange`, exiting on failure.

    Args:
        preset: A preset name accepted by
            :func:`core.mantecato_core.date_utils.resolve_date_range`
            (``"7d"``, ``"30d"``, ``"today"``, ...).

    Raises:
        typer.Exit: code 1 when *preset* is invalid.
    """
    from core.mantecato_core.date_utils import resolve_date_range

    date_range = resolve_date_range(preset)
    if not date_range:
        typer.echo("Invalid date range.", err=True)
        raise typer.Exit(1)
    return date_range


def parse_filters(values: list[str] | None):
    """Parse the repeated ``--filter`` query strings, returning a list."""
    from core.mantecato_core.filters import parse_filters_from_params

    return parse_filters_from_params(values or [])


def emit(data: Any, fmt: str) -> None:
    """Render *data* via :func:`format_output` and write to stdout."""
    typer.echo(format_output(data, fmt))


def get_or_die(value: Any, message: str, *, exit_code: int = 1) -> Any:
    """Return *value* unchanged; if falsy/``None``, print *message* and exit.

    Used by the CRUD commands to collapse the ``if result is None: ...
    raise typer.Exit`` pattern into a single call.
    """
    if value is None or value is False:
        typer.echo(message, err=True)
        raise typer.Exit(exit_code)
    return value


def run_with_range(
    service_fn: Callable[..., Any],
    website: str,
    range_str: str,
    fmt: str,
    **extra: Any,
) -> None:
    """Standard "bootstrap → resolve range → call service → emit" handshake.

    The four steps repeated at the bottom of every analytics command are
    folded into this one call.

    Args:
        service_fn: the service-layer function to invoke.
        website: website UUID (positional first arg to *service_fn*).
        range_str: date-range preset (``"7d"`` / ``"30d"`` / ``"today"`` / …).
        fmt: output format (``"table"`` / ``"json"`` / ``"csv"``).
        **extra: extra keyword arguments forwarded to *service_fn*.
    """
    bootstrap()
    emit(service_fn(website, resolve_range(range_str), **extra), fmt)


def run_query(
    query_fn: Callable[..., Any],
    website: str,
    range_str: str,
    filters: list[str] | None,
    fmt: str,
    **extra: Any,
) -> None:
    """Bootstrap-then-emit wrapper for the low-level query commands.

    Equivalent to :func:`run_with_range` but unpacks ``date_range`` into the
    ``(start, end)`` positional args expected by the raw query functions in
    :mod:`core.mantecato_core.queries`, and parses ``--filter`` arguments
    through :func:`parse_filters`.

    Args:
        query_fn: the query-engine function.
        website: website UUID.
        range_str: date-range preset (``"7d"`` etc.).
        filters: list of raw ``--filter`` strings (typer collects them).
        fmt: output format.
        **extra: extra keyword arguments forwarded to *query_fn*.
    """
    bootstrap()
    date_range = resolve_range(range_str)
    parsed = parse_filters(filters)
    emit(query_fn(website, date_range.start_date, date_range.end_date, parsed, **extra), fmt)


# -----------------------------------------------------------------------
# Legacy aliases kept for backward compatibility with existing imports.
# Prefer the names without leading underscore in new code.
# -----------------------------------------------------------------------
_bootstrap = bootstrap
_date_range_or_exit = resolve_range
_filters_from_cli = parse_filters
_emit = emit
