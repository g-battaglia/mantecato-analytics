"""Environment configuration helpers for the Mantecato Django project.

This module provides functions that read environment variables and validate
configuration values before Django settings are constructed. It is imported
early by ``mantecato/settings.py`` and must not import any Django models
or apps (only ``django.core.exceptions`` is safe at this stage).

Key responsibilities:
- Resolve the database URL with debug/test overrides.
- Validate that the database host is safe (prevent accidental production
  connections during development).
- Provide the SECRET_KEY with a clear error if missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

# Project root directory (one level above this file's parent ``mantecato/``).
BASE_DIR = Path(__file__).resolve().parent.parent

# Hostnames considered safe for DEBUG=True database connections.
# Any other host in DEBUG mode triggers an ImproperlyConfigured error
# unless ALLOW_REMOTE_DB is set, preventing accidental production writes.
_LOCAL_DB_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
    }
)


def _env(name: str, default: str = "") -> str:
    """Read an environment variable with an optional default.

    Args:
        name: The environment variable name.
        default: Value to return if the variable is unset. Defaults to ``""``.

    Returns:
        The environment variable's value, or *default*.
    """
    return os.environ.get(name, default)


def get_database_url(*, debug: bool = False) -> str:
    """Resolve the database URL from the environment.

    In debug mode a ``TEST_DATABASE_URL`` takes precedence; an empty result
    lets ``settings`` fall back to a local SQLite database.
    """
    if debug:
        return _env("TEST_DATABASE_URL") or _env("DATABASE_URL")
    return _env("DATABASE_URL")


def get_production_hosts() -> frozenset[str]:
    """Read the ``PRODUCTION_HOSTS`` environment variable as a set of hostnames.

    Production hosts are database hostnames that should *never* be connected
    to, regardless of the ``DEBUG`` setting. This acts as a hard safety net
    to prevent data corruption from development or CI runs.

    Returns:
        A frozenset of stripped, non-empty hostname strings parsed from
        the comma-separated ``PRODUCTION_HOSTS`` env var.
    """
    raw = _env("PRODUCTION_HOSTS", "")
    return frozenset(h.strip() for h in raw.split(",") if h.strip())


def get_db_hostname(database_url: str) -> str:
    """Extract the hostname from a database URL.

    Args:
        database_url: A PostgreSQL connection URL
            (e.g. ``"postgresql://user:pass@host:5432/db"``).

    Returns:
        The hostname component, or an empty string if the URL has no host.
    """
    parsed = urlparse(database_url)
    return parsed.hostname or ""


def validate_database_host(database_url: str, debug: bool) -> None:
    """Validate that the database host is safe to connect to.

    Implements two safety checks:

    1. **Production blocklist:** If the hostname appears in the
       ``PRODUCTION_HOSTS`` env var, connection is always refused. This
       prevents any code path from accidentally writing to production.

    2. **Debug remote guard:** When ``DEBUG=True``, only loopback hostnames
       (localhost and 127.0.0.1) are allowed unless ``ALLOW_REMOTE_DB=True`` is
       set. This catches misconfigured ``.env`` files that point at a remote
       database during development.

    Args:
        database_url: The full database connection URL.
        debug: Whether Django is running in debug mode.

    Raises:
        ImproperlyConfigured: If the hostname fails either safety check.
    """
    hostname = get_db_hostname(database_url)
    if not hostname:
        return

    production_hosts = get_production_hosts()
    if hostname in production_hosts:
        raise ImproperlyConfigured(
            f"Database host '{hostname}' is listed in PRODUCTION_HOSTS. "
            "Refusing to connect to a production database."
        )

    if debug and hostname not in _LOCAL_DB_HOSTS:
        # Allow explicit bypass for legitimate remote dev databases
        if _env("ALLOW_REMOTE_DB", "").lower() in ("1", "true", "yes"):
            return
        raise ImproperlyConfigured(
            f"DEBUG=True but database host '{hostname}' is not a recognized "
            f"local/test host. Allowed in DEBUG mode: {sorted(_LOCAL_DB_HOSTS)}. "
            "Set ALLOW_REMOTE_DB=True to bypass or DEBUG=False for production."
        )


def require_database_url(database_url: str, *, debug: bool) -> None:
    """Fail fast when no database is configured in production.

    Mantecato requires PostgreSQL; the SQLite fallback in ``settings`` is only
    for quick local development (``DEBUG=True``). With ``DEBUG=False`` a missing
    ``DATABASE_URL`` would silently fall back to SQLite and break the
    PostgreSQL-only migrations (e.g. ``core.0002`` runs ``SET DEFAULT now()``),
    so we fail with a clear message instead of an opaque mid-migration crash.

    Args:
        database_url: The resolved database URL (may be empty).
        debug: Whether Django is running in debug mode.

    Raises:
        ImproperlyConfigured: If *database_url* is empty and *debug* is False.
    """
    if not database_url and not debug:
        raise ImproperlyConfigured(
            "DATABASE_URL must be set when DEBUG=False. Mantecato requires "
            "PostgreSQL in production; the SQLite fallback is development-only."
        )


def open_hosts_warning(allowed_hosts: list[str]) -> str | None:
    """Return a warning message when ALLOWED_HOSTS is wide open, else None.

    ``ALLOWED_HOSTS == ['*']`` disables Django's Host-header validation. That
    keeps a first deploy zero-config, but should be tightened in production.
    When running on Railway we can suggest the exact value to set, derived from
    the ``RAILWAY_PUBLIC_DOMAIN`` system variable.

    Args:
        allowed_hosts: The resolved ``ALLOWED_HOSTS`` list.

    Returns:
        A human-readable warning string, or ``None`` if hosts are restricted.
    """
    if allowed_hosts != ["*"]:
        return None
    railway_domain = _env("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        return (
            f"ALLOWED_HOSTS is open to all hosts ('*'). On Railway, set "
            f"ALLOWED_HOSTS={railway_domain},healthcheck.railway.app to restrict it."
        )
    return (
        "ALLOWED_HOSTS is open to all hosts ('*'). Set the ALLOWED_HOSTS "
        "environment variable (comma-separated) to restrict it in production."
    )


def get_secret_key() -> str:
    """Read the ``SECRET_KEY`` from the environment, raising if missing.

    The secret key is critical for session signing, CSRF tokens, and the
    deterministic session UUID generation in the tracker. It must be set
    before Django can start.

    Returns:
        The secret key string.

    Raises:
        ImproperlyConfigured: If ``SECRET_KEY`` is empty or unset.
    """
    key = _env("SECRET_KEY")
    if not key:
        raise ImproperlyConfigured("SECRET_KEY must be set in environment or .env file.")
    return key
