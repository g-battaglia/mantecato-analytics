"""Shared engine for importing data from an Umami PostgreSQL database.

This module factors out the table-copy logic used by two management commands
with very different risk profiles:

- :mod:`apps.core.management.commands.importumami` — the **full** import. It
  copies *configuration* too (users, teams, websites, segments, reports) and is
  therefore destructive to the Mantecato configuration: importing a foreign
  ``website`` row, or wiping/replacing the existing one, breaks event ingestion
  because the tracker posts a hardcoded ``website_id``. It is guarded behind an
  explicit ``--include-config`` flag plus an interactive confirmation.
- :mod:`apps.core.management.commands.importumamidata` — the **data-only**
  import. It copies analytics rows only (sessions, events, event data, session
  data, revenue), never touching configuration, and can target a single website
  by remapping the source ``website_id`` onto an existing Mantecato website.

Both share the same column mapping, defensive value adaptation (timestamp →
boolean, ``revenue`` NULL → 0, JSON wrapping, width truncation) and batched
``executemany`` with ``ON CONFLICT (pk) DO NOTHING`` for idempotency.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import psycopg
from django.db import connection, transaction
from psycopg.types.json import Jsonb
from rich.console import Console

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Any

    from rich.progress import Progress

BATCH_SIZE = 10_000

# (label, source_table, dest_table, is_user). Order satisfies the virtual
# dependencies (users/teams/websites before sessions/events, etc.).
_TABLES_ORDER = [
    ("users", '"user"', "mantecato_user", True),
    ("teams", "team", "team", False),
    ("team_users", "team_user", "team_user", False),
    ("websites", "website", "website", False),
    ("sessions", "session", "session", False),
    ("events", "website_event", "website_event", False),
    ("event_data", "event_data", "event_data", False),
    ("session_data", "session_data", "session_data", False),
    ("revenue", "revenue", "revenue", False),
    ("segments", "segment", "segment", False),
    ("reports", "report", "report", False),
]

# Analytics tables. Everything else in ``_TABLES_ORDER`` is *configuration*.
# These are the only tables the data-only import touches, and the only ones
# carrying a ``website_id`` column usable for single-site filtering/remapping.
_DATA_TABLES = {"sessions", "events", "event_data", "session_data", "revenue"}

# Per-table source→destination column renames (see the module docstring of the
# original importer for the rationale behind ``deleted_at``→``is_deleted`` and
# ``parameters``→``name_filters``).
_SRC_TO_DST_COL = {
    "website": {"website_id": "id", "deleted_at": "is_deleted"},
    "team": {"team_id": "id"},
    "segment": {"segment_id": "id", "parameters": "name_filters"},
    "report": {"report_id": "id"},
}

_DST_PK = {
    "website": "id",
    "session": "session_id",
    "website_event": "event_id",
    "event_data": "event_data_id",
    "session_data": "session_data_id",
    "team": "id",
    "team_user": "team_user_id",
    "revenue": "revenue_id",
    "segment": "id",
    "report": "id",
}

_USER_COL_MAP = {"user_id": "id"}
_USER_VALID_COLS = {
    "user_id",
    "username",
    "password",
    "role",
    "created_at",
    "updated_at",
    "deleted_at",
}


class UmamiImporter:
    """Copy rows from an Umami database into the Mantecato schema.

    Each per-table copy runs inside its own :func:`django.db.transaction.atomic`
    block so a mid-table failure rolls back only that table. ``ON CONFLICT (pk)
    DO NOTHING`` keeps the import idempotent.

    Args:
        source_dsn: PostgreSQL connection string for the source Umami database.
        console: Optional Rich console for progress output.
        data_only: When ``True``, copy only the analytics tables
            (:data:`_DATA_TABLES`) and never the configuration tables.
        since_date: Optional cutoff; only analytics rows with
            ``created_at >= since_date`` are copied.
        skip_events: When ``True``, skip the analytics tables (mutually
            exclusive in practice with *data_only*).
        source_website: Optional Umami ``website_id`` (UUID) to filter the
            analytics tables by — enables single-site import.
        target_website: Optional Mantecato ``website_id`` (UUID) to remap the
            copied analytics rows onto. Requires *source_website*.

    Raises:
        ValueError: If *target_website* is given without *source_website*, or if
            either is not a valid UUID.
    """

    def __init__(
        self,
        source_dsn: str,
        console: Console | None = None,
        *,
        data_only: bool = False,
        since_date: datetime | None = None,
        skip_events: bool = False,
        source_website: str | None = None,
        target_website: str | None = None,
    ) -> None:
        self.source_dsn = source_dsn
        self.console = console or Console()
        self.data_only = data_only
        self.since_date = since_date
        self.skip_events = skip_events
        # Validate/normalise the UUIDs up front so they are safe to interpolate
        # into the WHERE clause and as a remap value.
        self.source_website = str(uuid.UUID(str(source_website))) if source_website else None
        self.target_website = str(uuid.UUID(str(target_website))) if target_website else None
        if self.target_website and not self.source_website:
            raise ValueError("target_website requires source_website.")

    def connect(self) -> psycopg.Connection:
        """Open an autocommit connection to the source Umami database.

        Returns:
            An open psycopg connection.

        Raises:
            ConnectionError: If the connection cannot be established.
        """
        try:
            return psycopg.connect(self.source_dsn, autocommit=True)
        except Exception as exc:  # noqa: BLE001 — surfaced as a clean error
            raise ConnectionError(f"Cannot connect to source database: {exc}") from exc

    def _tables(self) -> list[tuple[str, str, str, bool]]:
        """Return the tables to process given the current mode.

        In ``data_only`` mode only :data:`_DATA_TABLES` are returned; otherwise
        every table in :data:`_TABLES_ORDER` is returned.
        """
        return [t for t in _TABLES_ORDER if not self.data_only or t[0] in _DATA_TABLES]

    def _where_clause(self, label: str) -> str:
        """Build the ``WHERE`` clause for a table from the since/website filters.

        Both filters only apply to analytics tables (:data:`_DATA_TABLES`); the
        UUID has already been validated in ``__init__`` so interpolation is safe.

        Args:
            label: The logical table label (e.g. ``"events"``).

        Returns:
            A SQL ``WHERE`` fragment (with leading space) or ``""``.
        """
        clauses = []
        if label in _DATA_TABLES:
            if self.since_date:
                clauses.append(f"created_at >= '{self.since_date.isoformat()}'")
            if self.source_website:
                clauses.append(f"website_id = '{self.source_website}'")
        return (" WHERE " + " AND ".join(clauses)) if clauses else ""

    def source_counts(self, src: psycopg.Connection) -> dict[str, Any]:
        """Return per-table source row counts honouring the active filters.

        Args:
            src: An open connection to the source database.

        Returns:
            A mapping of table label to row count (or ``"N/A"`` on error).
        """
        result: dict[str, Any] = {}
        with src.cursor() as cur:
            for label, src_table, _, _ in self._tables():
                where = self._where_clause(label)
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {src_table}{where}")
                    result[label] = cur.fetchone()[0]
                except Exception:  # noqa: BLE001
                    result[label] = "N/A"
        return result

    def run(self, src: psycopg.Connection, progress: Progress) -> None:
        """Copy every selected table from *src* into the Mantecato database.

        Args:
            src: An open connection to the source database.
            progress: A Rich progress instance for per-table progress bars.
        """
        for label, src_table, dst_table, is_user in self._tables():
            if self.skip_events and label in _DATA_TABLES:
                self.console.print(f"  [dim]Skipping {label} (--skip-events)[/dim]")
                continue
            self._copy_table(src, src_table, dst_table, is_user, label, progress)

    def replace_target_data(self) -> None:
        """Delete the destination analytics rows for the target website.

        Only valid in single-site mode; used by the ``--replace`` option so the
        imported data overwrites (rather than adds to) the existing rows for
        that website. Configuration tables are never touched.
        """
        if not self.target_website:
            raise ValueError("replace_target_data requires target_website.")
        with connection.cursor() as cur:
            for table in ("revenue", "session_data", "event_data", "website_event", "session"):
                cur.execute(f"DELETE FROM {table} WHERE website_id = %s", [self.target_website])

    def _copy_table(self, src, src_table, dst_table, is_user, label, progress) -> None:
        """Copy one source table into its destination, atomically.

        ``transaction.atomic`` bounds a mid-table failure to this table only;
        earlier tables (already committed) stay intact.
        """
        where = self._where_clause(label)
        with src.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {src_table}{where}")
            total = cur.fetchone()[0]

        if total == 0:
            return

        task = progress.add_task(f"Importing {label}", total=total)

        with src.cursor() as cur, transaction.atomic():
            cur.execute(f"SELECT * FROM {src_table}{where}")
            columns = [desc[0] for desc in cur.description]

            if is_user:
                self._import_users(cur, columns, task, progress)
            else:
                self._import_generic(cur, columns, dst_table, task, progress)

    def _import_users(self, cur, columns, task, progress) -> None:
        """Import user rows, converting Umami's bare bcrypt hashes for Django.

        Umami stores ``$2b$...`` hashes; Django needs a ``bcrypt$`` prefix to
        select the right hasher.
        """
        indices = []
        dst_columns = []
        for i, c in enumerate(columns):
            if c in _USER_VALID_COLS:
                indices.append(i)
                dst_columns.append(_USER_COL_MAP.get(c, c))

        pw_dst_idx = dst_columns.index("password") if "password" in dst_columns else None
        placeholders = ", ".join(["%s"] * len(dst_columns))
        col_list = ", ".join(dst_columns)
        insert_sql = (
            f"INSERT INTO mantecato_user ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO NOTHING"
        )

        from django.utils import timezone

        batch = []
        for row in cur:
            row = [row[i] for i in indices]
            if pw_dst_idx is not None and row[pw_dst_idx]:
                raw_hash = row[pw_dst_idx]
                if raw_hash.startswith("$2"):
                    row[pw_dst_idx] = f"bcrypt${raw_hash}"
            for j, col in enumerate(dst_columns):
                if col in ("created_at", "updated_at") and row[j] is None:
                    row[j] = timezone.now()
            batch.append(tuple(row))

            if len(batch) >= BATCH_SIZE:
                self._execute_batch(insert_sql, batch)
                progress.update(task, advance=len(batch))
                batch = []

        if batch:
            self._execute_batch(insert_sql, batch)
            progress.update(task, advance=len(batch))

    def _import_generic(self, cur, columns, dst_table, task, progress) -> None:
        """Import a non-user table, mapping source columns to destination columns.

        Columns absent in the destination are dropped; renames come from
        :data:`_SRC_TO_DST_COL`; over-long strings are truncated to the
        destination width; and ``website_id`` is remapped to *target_website*
        when single-site import is active.
        """
        dst_meta = self._get_dst_columns(dst_table)
        col_map = _SRC_TO_DST_COL.get(dst_table, {})
        indices = []
        used_cols = []
        for i, c in enumerate(columns):
            mapped = col_map.get(c, c)
            if mapped in dst_meta:
                indices.append(i)
                used_cols.append(mapped)

        if not used_cols:
            return

        max_lengths = [dst_meta.get(c) for c in used_cols]
        placeholders = ", ".join(["%s"] * len(used_cols))
        col_list = ", ".join(f'"{c}"' for c in used_cols)
        pk_col = _DST_PK.get(dst_table, used_cols[0])
        insert_sql = (
            f"INSERT INTO {dst_table} ({col_list}) VALUES ({placeholders}) "
            f'ON CONFLICT ("{pk_col}") DO NOTHING'
        )

        batch = []
        for row in cur:
            filtered = tuple(row[i] for i in indices)
            batch.append(self._adapt_row_with_cols(filtered, used_cols, max_lengths))
            if len(batch) >= BATCH_SIZE:
                self._execute_batch(insert_sql, batch)
                progress.update(task, advance=len(batch))
                batch = []

        if batch:
            self._execute_batch(insert_sql, batch)
            progress.update(task, advance=len(batch))

    @staticmethod
    def _get_dst_columns(table_name: str) -> dict[str, int | None]:
        """Return destination column names mapped to their max character length.

        ``character_maximum_length`` is ``None`` for non-character types (uuid,
        integer, jsonb, timestamptz) and an ``int`` for ``varchar``/``char``.
        """
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = 'public'",
                [table_name],
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def _adapt_row_with_cols(self, row, col_names, max_lengths) -> tuple:
        """Adapt a source row for insertion, reconciling Umami ↔ Mantecato.

        Transformations (earlier, column-specific rules win over truncation):

            - ``website_id`` → remapped to *target_website* in single-site mode.
            - ``is_deleted`` → ``deleted_at`` timestamp converted to boolean.
            - ``revenue`` → ``0`` when NULL (NOT NULL in Mantecato).
            - dict/list → :class:`~psycopg.types.json.Jsonb`.
            - NULL ``created_at``/``updated_at`` → ``timezone.now()``.
            - over-long strings → truncated to the destination column width.
        """
        from django.utils import timezone

        now = timezone.now()
        result = []
        for value, col, max_len in zip(row, col_names, max_lengths, strict=True):
            if col == "website_id" and self.target_website:
                result.append(self.target_website)
            elif col == "is_deleted":
                result.append(value is not None)
            elif col == "revenue" and value is None:
                result.append(0)
            elif isinstance(value, (dict, list)):
                result.append(Jsonb(value))
            elif value is None and col in ("created_at", "updated_at"):
                result.append(now)
            elif isinstance(value, str) and max_len is not None and len(value) > max_len:
                result.append(value[:max_len])
            else:
                result.append(value)
        return tuple(result)

    @staticmethod
    def _execute_batch(sql: str, batch: list[tuple]) -> None:
        """Execute one batch of parameterised INSERTs against the destination."""
        with connection.cursor() as cur:
            cur.executemany(sql, batch)
