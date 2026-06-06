"""Sync query execution bridge using Django's psycopg3 cursor.

Uses ``django.db.connections['default'].cursor()`` for all SQL execution.
Parameter placeholders use ``{{name}}`` / ``{{name::type}}`` syntax,
converted to ``%s`` / ``%s::type`` (psycopg3) before execution.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from decimal import Decimal
from typing import Any

from django.db import connections

logger = logging.getLogger(__name__)

DEFAULT_DB_ALIAS = "default"

# Threshold (milliseconds) above which an individual SQL query is logged
# as a warning.  Tunable via the ``SLOW_QUERY_THRESHOLD_MS`` Django setting.
DEFAULT_SLOW_QUERY_THRESHOLD_MS = 100.0

# Per-thread query timing buffer used by the optional ``QueryTimingMiddleware``
# to attach a ``Server-Timing`` header.  Each entry is a tuple of
# ``(label, duration_ms)``.  Lives in ``threading.local`` because Django views
# are sync and may share the same process across requests.
_query_log = threading.local()


def _slow_threshold_ms() -> float:
    """Return the slow-query threshold (ms), reading it lazily from settings.

    The setting is fetched on each call so that test overrides via
    ``override_settings`` take effect without restarting the process.  Falls
    back to :data:`DEFAULT_SLOW_QUERY_THRESHOLD_MS` if the setting is missing
    or non-numeric.
    """
    try:
        from django.conf import settings

        value = getattr(settings, "SLOW_QUERY_THRESHOLD_MS", DEFAULT_SLOW_QUERY_THRESHOLD_MS)
        return float(value)
    except Exception:
        return DEFAULT_SLOW_QUERY_THRESHOLD_MS


def reset_query_log() -> None:
    """Clear the per-thread query log.

    Called by :class:`mantecato.middleware.QueryTimingMiddleware` at the start
    of every request so that the next request's timing list starts empty.
    """
    _query_log.entries = []


def get_query_log() -> list[tuple[str, float]]:
    """Return the per-thread query log captured since the last reset.

    Each entry is ``(label, duration_ms)`` where ``label`` is the calling
    function/module that produced the SQL.  Returns an empty list when the
    middleware has not initialised the log for the current thread.
    """
    return getattr(_query_log, "entries", [])


def _caller_label() -> str:
    """Derive a short label for the caller of :func:`raw_query`.

    Walks up the call stack via :func:`sys._getframe` (cheap frame pointer
    traversal, no ``FrameSummary`` / source-line materialisation) until it
    finds the first frame outside this module, returning
    ``"<module>.<function>"``.  Used as the ``Server-Timing`` name and the
    slow-query log prefix.

    Computed lazily by :func:`raw_query` only when a consumer exists (the
    request-scoped query log or a slow-query warning), so the common case
    pays nothing.
    """
    try:
        frame = sys._getframe(1)
    except ValueError:  # pragma: no cover - depth guard
        return "raw_query"
    while frame is not None:
        filename = frame.f_code.co_filename
        if "mantecato_core/database.py" not in filename:
            module = filename.rsplit("/", 1)[-1].removesuffix(".py")
            return f"{module}.{frame.f_code.co_name}"
        frame = frame.f_back
    return "raw_query"


_PARAM_RE = re.compile(r"\{\{\s*(\w+)(?:::([\w\[\]]+))?\s*\}\}|\{\s*(\w+)(?:::([\w\[\]]+))?\s*\}")


def _substitute_params(sql: str, params: dict[str, Any]) -> tuple[str, list[Any]]:
    """Replace ``{{name}}`` / ``{{name::type}}`` placeholders with ``%s`` / ``%s::type``.

    For each match, the corresponding value from *params* is appended to the
    argument list in order.  Type casts (``::uuid``, ``::timestamptz``, etc.) are
    preserved so the SQL semantic stays identical to the legacy asyncpg version.

    Example::

        _substitute_params(
            "SELECT * FROM t WHERE id = {{id::uuid}} AND name = {{name}}",
            {"id": "abc-123", "name": "test"},
        )
        # => ("SELECT * FROM t WHERE id = %s::uuid AND name = %s", ["abc-123", "test"])
    """
    args: list[Any] = []

    def _replacer(m: re.Match) -> str:
        name = m.group(1) or m.group(3)
        type_cast = f"::{m.group(2) or m.group(4)}" if (m.group(2) or m.group(4)) else ""
        args.append(params.get(name))
        return f"%s{type_cast}"

    query = _PARAM_RE.sub(_replacer, sql)
    return query, args


def _convert_row(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a DB-API 2.0 row tuple to a dict, casting ``Decimal`` to ``float``."""
    return {
        key: (float(value) if isinstance(value, Decimal) else value)
        for key, value in zip(columns, row, strict=True)
    }


def _get_cursor():
    """Return a cursor on the default database connection."""
    return connections[DEFAULT_DB_ALIAS].cursor()


def raw_query(
    sql: str, params: dict[str, Any] | None = None, *, _retries: int = 2
) -> list[dict[str, Any]]:
    """Execute a raw SQL query and return all rows as list[dict].

    Parameters are provided as a dict of named values that are substituted
    into the SQL string.  See :func:`_substitute_params` for the placeholder
    syntax.

    Transient connection errors trigger up to *_retries* retries with
    exponential back-off, matching the behaviour of the legacy async version.
    """
    if params is None:
        params = {}
    query, args = _substitute_params(sql, params)
    last_exc: Exception | None = None
    for attempt in range(_retries + 1):
        try:
            with _get_cursor() as cursor:
                started = time.perf_counter()
                cursor.execute(query, args)
                duration_ms = (time.perf_counter() - started) * 1000.0
                # Resolve the caller label lazily: only the request-scoped
                # query log or a slow-query warning consume it, so the
                # stack walk is skipped entirely on the hot path.
                entries = getattr(_query_log, "entries", None)
                is_slow = duration_ms >= _slow_threshold_ms()
                if entries is not None or is_slow:
                    label = _caller_label()
                    if entries is not None:
                        entries.append((label, duration_ms))
                    if is_slow:
                        logger.warning("Slow DB query %s took %.1fms", label, duration_ms)
                if cursor.description is None:
                    return []
                columns = [col[0] for col in cursor.description]
                return [_convert_row(columns, row) for row in cursor.fetchall()]
        except (OSError, ConnectionError, TimeoutError) as exc:
            last_exc = exc
            if attempt < _retries:
                delay = 0.5 * (attempt + 1)
                logger.warning("DB query retry %d/%d after %s", attempt + 1, _retries, exc)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def raw_query_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Execute a query and return the first row, or ``None`` if no results."""
    results = raw_query(sql, params)
    return results[0] if results else None


def paged_raw_query(
    sql: str,
    params: dict[str, Any],
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Execute a paginated query.

    Returns ``{"data": [...], "count": int, "page": int, "pageSize": int}``.
    """
    count_sql = f"SELECT COUNT(*) AS count FROM ({sql}) AS t"
    count_row = raw_query_one(count_sql, params)
    count = int(count_row["count"]) if count_row else 0

    paged_sql = f"{sql} LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    data = raw_query(paged_sql, params)

    return {"data": data, "count": count, "page": page, "pageSize": page_size}


def get_date_trunc(granularity: str) -> str:
    """Return a ``date_trunc`` SQL expression for the given granularity."""
    valid = ["minute", "hour", "day", "week", "month", "year"]
    if granularity not in valid:
        return "date_trunc('day', we.created_at)"
    return f"date_trunc('{granularity}', we.created_at)"
