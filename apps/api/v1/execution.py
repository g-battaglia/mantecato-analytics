"""Bounded, read-only execution support for the additive API v1 handlers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.db import connection, transaction

from apps.api.v1.catalog import STATEMENT_TIMEOUT_MS

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def analytics_transaction(*, timeout_ms: int = STATEMENT_TIMEOUT_MS) -> Iterator[None]:
    """Run new analytics queries in one bounded snapshot.

    Authentication may update API-key metadata before this block. The read-only
    setting therefore applies to the analytics transaction, not to middleware.
    Django's test runner may already own an outer transaction; in that case a
    nested block cannot change transaction characteristics and tests rely on
    static no-write assertions plus their isolated database.
    """
    already_atomic = connection.in_atomic_block
    with transaction.atomic():
        with connection.cursor() as cursor:
            if not already_atomic:
                cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = %s", [max(1, int(timeout_ms))])
            cursor.execute("SET LOCAL lock_timeout = %s", [min(max(1, int(timeout_ms)), 5_000)])
        yield


def fetch_all(sql: str, params: list[object]) -> list[dict[str, object]]:
    """Execute bounded SELECT SQL and return dictionaries."""
    statement = sql.lstrip().upper()
    if not (statement.startswith("WITH") or statement.startswith("SELECT")):
        raise ValueError("API v1 analytics executor accepts SELECT statements only")
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description is None:
            return []
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
