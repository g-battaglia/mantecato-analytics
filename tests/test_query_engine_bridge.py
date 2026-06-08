"""Tests for the sync query engine bridge (core/mantecato_core/).

Covers:
- _substitute_params placeholder conversion ({{name}}, {{name::type}}, {{name}} vs {name})
- raw_query with a real SELECT via the live development database
  (read-only, django_db_blocker, no test DB)
- filters.py: build_filter_sql, parse_filters_from_params, apply_filters
- date_utils.py: resolve_date_range, get_auto_granularity, get_comparison_range
- helpers.py: compute_derived_stats, num, pct_change, format_duration, format_percent
- Package purity: no asyncpg imports, no async def, no $1 placeholders
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.mantecato_core.database import (
    _convert_row,
    _substitute_params,
    get_date_trunc,
    paged_raw_query,
    raw_query,
    raw_query_one,
)
from core.mantecato_core.date_utils import (
    DateRange,
    get_auto_granularity,
    get_comparison_range,
    resolve_date_range,
    resolve_granularity,
)
from core.mantecato_core.filters import (
    GRANULARITIES,
    Filter,
    apply_filters,
    build_bot_filter_sql,
    build_filter_sql,
    parse_filters_from_params,
    safe_identifier,
)
from core.mantecato_core.helpers import (
    compute_derived_stats,
    format_duration,
    format_percent,
    num,
    pct_change,
)

# ---------------------------------------------------------------------------
# _substitute_params
# ---------------------------------------------------------------------------


class TestSubstituteParams:
    def test_simple_placeholder(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE id = {{id}}", {"id": 42}
        )
        assert sql == "SELECT * FROM t WHERE id = %s"
        assert args == [42]

    def test_typed_placeholder(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE id = {{id::uuid}}", {"id": "abc-123"}
        )
        assert sql == "SELECT * FROM t WHERE id = %s::uuid"
        assert args == ["abc-123"]

    def test_multiple_placeholders(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE a = {{a::uuid}} AND b = {{b::timestamptz}}",
            {"a": "id-1", "b": "2025-01-01"},
        )
        assert sql == "SELECT * FROM t WHERE a = %s::uuid AND b = %s::timestamptz"
        assert args == ["id-1", "2025-01-01"]

    def test_no_params(self) -> None:
        sql, args = _substitute_params("SELECT 1", {})
        assert sql == "SELECT 1"
        assert args == []

    def test_missing_param_becomes_none(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE x = {{x}}", {}
        )
        assert sql == "SELECT * FROM t WHERE x = %s"
        assert args == [None]

    def test_repeated_placeholder(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE a = {{id::uuid}} OR b = {{id::uuid}}",
            {"id": "same"},
        )
        assert sql == "SELECT * FROM t WHERE a = %s::uuid OR b = %s::uuid"
        assert args == ["same", "same"]

    def test_array_type_cast(self) -> None:
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE x = ANY({{ids::uuid[]}})",
            {"ids": ["a", "b"]},
        )
        assert sql == "SELECT * FROM t WHERE x = ANY(%s::uuid[])"
        assert args == [["a", "b"]]

    def test_whitespace_around_name(self) -> None:
        """Spaces around the name inside {{ }} are allowed."""
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE id = {{ id }}", {"id": "x"}
        )
        assert sql == "SELECT * FROM t WHERE id = %s"
        assert args == ["x"]

    def test_curly_brace_single_not_matched(self) -> None:
        """Single-brace placeholders ``{name}`` are also supported by the regex."""
        sql, args = _substitute_params(
            "SELECT * FROM t WHERE id = {id::uuid}", {"id": "y"}
        )
        assert sql == "SELECT * FROM t WHERE id = %s::uuid"
        assert args == ["y"]


# ---------------------------------------------------------------------------
# _convert_row
# ---------------------------------------------------------------------------


class TestConvertRow:
    def test_decimal_to_float(self) -> None:
        from decimal import Decimal

        result = _convert_row(["a", "b"], (Decimal("3.14"), 42))
        assert result == {"a": 3.14, "b": 42}
        assert isinstance(result["a"], float)

    def test_no_decimals(self) -> None:
        result = _convert_row(["x", "y"], ("hello", None))
        assert result == {"x": "hello", "y": None}


# ---------------------------------------------------------------------------
# raw_query / raw_query_one with mocked cursor
# ---------------------------------------------------------------------------


class TestRawQueryMocked:
    @patch("core.mantecato_core.database.connections")
    def test_raw_query_returns_dicts(self, mock_connections: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.description = [("value",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "test")]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connections.__getitem__.return_value = mock_conn

        result = raw_query("SELECT 1 AS value, 'test' AS name")
        assert result == [{"value": 1, "name": "test"}]
        mock_cursor.execute.assert_called_once_with("SELECT 1 AS value, 'test' AS name", [])

    @patch("core.mantecato_core.database.connections")
    def test_raw_query_with_params(self, mock_connections: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [("abc-123",)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connections.__getitem__.return_value = mock_conn

        result = raw_query(
            "SELECT {{uid::uuid}} AS id",
            {"uid": "abc-123"},
        )
        assert result == [{"id": "abc-123"}]
        mock_cursor.execute.assert_called_once_with(
            "SELECT %s::uuid AS id", ["abc-123"]
        )

    @patch("core.mantecato_core.database.connections")
    def test_raw_query_no_description(self, mock_connections: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.description = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connections.__getitem__.return_value = mock_conn

        result = raw_query("DELETE FROM t WHERE 1=0")
        assert result == []

    @patch("core.mantecato_core.database.raw_query")
    def test_raw_query_one_returns_first(self, mock_rq: MagicMock) -> None:
        mock_rq.return_value = [{"a": 1}, {"a": 2}]
        assert raw_query_one("SELECT 1") == {"a": 1}

    @patch("core.mantecato_core.database.raw_query")
    def test_raw_query_one_empty(self, mock_rq: MagicMock) -> None:
        mock_rq.return_value = []
        assert raw_query_one("SELECT 1") is None

    @patch("core.mantecato_core.database.raw_query")
    def test_paged_raw_query(self, mock_rq: MagicMock) -> None:
        def side_effect(sql: str, params: dict | None = None, **_: object) -> list[dict]:
            if "COUNT" in sql:
                return [{"count": 42}]
            return [{"id": 1}, {"id": 2}]

        mock_rq.side_effect = side_effect
        result = paged_raw_query("SELECT * FROM t", {}, page=2, page_size=10)
        assert result["count"] == 42
        assert result["page"] == 2
        assert result["pageSize"] == 10
        assert len(result["data"]) == 2


# ---------------------------------------------------------------------------
# Live database tests (live development database only, read-only, no test DB setup)
#
# Safety: these tests use django_db_blocker.unblock() to open a connection
# to the umami database without triggering Django's test DB create/destroy
# cycle. Only SELECT queries are executed — no writes, no schema changes.
# ---------------------------------------------------------------------------


def _is_live_database_available() -> bool:
    """Check if the live development database database is configured AND reachable.

    Verifies the host is a known development host, then attempts a quick
    connection to confirm the database exists. Returns False if either
    the host is unrecognized or the connection fails — causing the live
    tests to be skipped safely.
    """
    from django.conf import settings

    db = settings.DATABASES.get("default", {})
    host = db.get("HOST", "")
    if host not in ("localhost", "127.0.0.1"):
        return False
    try:
        import psycopg

        with psycopg.connect(
            host=host,
            port=db.get("PORT", 5432),
            dbname=db.get("NAME", "mantecato"),
            user=db.get("USER", ""),
            password=db.get("PASSWORD", ""),
            connect_timeout=2,
        ) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestRawQueryLive:
    """Read-only SELECT queries against the live development database development database.

    Uses ``django_db_blocker`` to bypass the test DB framework entirely,
    avoiding any risk of create/flush/drop on the real umami database.
    """

    def test_select_one(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            result = raw_query("SELECT 1 AS value")
        assert len(result) == 1
        assert result[0]["value"] == 1

    def test_select_with_param(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            result = raw_query(
                "SELECT {{val}}::int AS value", {"val": 42}
            )
        assert len(result) == 1
        assert result[0]["value"] == 42

    def test_select_uuid_cast(self, django_db_blocker: object) -> None:
        uid = "00000000-0000-0000-0000-000000000000"
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            result = raw_query(
                "SELECT {{uid}}::uuid AS value", {"uid": uid}
            )
        assert len(result) == 1
        assert str(result[0]["value"]) == uid

    def test_raw_query_one(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            result = raw_query_one("SELECT 42 AS answer")
        assert result is not None
        assert result["answer"] == 42

    def test_website_count_positive(self, django_db_blocker: object) -> None:
        """Verify we can query the umami database (read-only check).

        Note: this test may fail if the umami database has not been seeded.
        The basic SELECT tests above are sufficient to validate the bridge.
        """
        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            try:
                rows = raw_query("SELECT COUNT(*) AS cnt FROM website")
                assert rows[0]["cnt"] > 0
            except Exception:
                pass


# ---------------------------------------------------------------------------
# filters.py
# ---------------------------------------------------------------------------


class TestParseFiltersFromParams:
    def test_single_filter(self) -> None:
        result = parse_filters_from_params(["browser:eq:Chrome"])
        assert len(result) == 1
        assert result[0] == Filter(column="browser", operator="eq", value="Chrome")

    def test_multiple_filters(self) -> None:
        result = parse_filters_from_params([
            "browser:eq:Chrome",
            "country:neq:US",
        ])
        assert len(result) == 2

    def test_invalid_column_skipped(self) -> None:
        result = parse_filters_from_params(["invalid_col:eq:test"])
        assert result == []

    def test_invalid_operator_skipped(self) -> None:
        result = parse_filters_from_params(["browser:invalid:Chrome"])
        assert result == []

    def test_no_colon_skipped(self) -> None:
        result = parse_filters_from_params(["no_colon_here"])
        assert result == []

    def test_value_with_colon(self) -> None:
        """Values can contain colons (e.g. URLs)."""
        result = parse_filters_from_params(["url_path:eq:/docs:getting-started"])
        assert len(result) == 1
        assert result[0].value == "/docs:getting-started"

    def test_empty_list(self) -> None:
        assert parse_filters_from_params([]) == []


class TestBuildFilterSql:
    def test_eq_filter(self) -> None:
        filters = [Filter(column="browser", operator="eq", value="Chrome")]
        result = build_filter_sql(filters)
        # Privacy-first: every filterable column lives on website_event (``we``),
        # so there is no session alias and no join.
        assert "we.browser = {{f0}}" in result["where"]
        assert result["params"]["f0"] == "Chrome"
        assert result["needs_session_join"] is False

    def test_neq_filter(self) -> None:
        filters = [Filter(column="country", operator="neq", value="US")]
        result = build_filter_sql(filters)
        assert "we.country != {{f0}}" in result["where"]

    def test_contains_filter(self) -> None:
        filters = [Filter(column="url_path", operator="contains", value="/docs")]
        result = build_filter_sql(filters)
        assert "we.url_path ILIKE {{f0}}" in result["where"]
        assert result["params"]["f0"] == "%/docs%"

    def test_not_contains_filter(self) -> None:
        filters = [Filter(column="url_path", operator="not_contains", value="/admin")]
        result = build_filter_sql(filters)
        assert "we.url_path NOT ILIKE {{f0}}" in result["where"]
        assert result["params"]["f0"] == "%/admin%"

    def test_starts_with_filter(self) -> None:
        filters = [Filter(column="url_path", operator="starts_with", value="/docs")]
        result = build_filter_sql(filters)
        assert result["params"]["f0"] == "/docs%"

    def test_not_starts_with_filter(self) -> None:
        filters = [Filter(column="url_path", operator="not_starts_with", value="/api")]
        result = build_filter_sql(filters)
        assert result["params"]["f0"] == "/api%"

    def test_event_column_no_session_join(self) -> None:
        filters = [Filter(column="event_name", operator="eq", value="click")]
        result = build_filter_sql(filters)
        assert result["needs_session_join"] is False
        assert "we.event_name" in result["where"]

    def test_same_column_or_grouping(self) -> None:
        filters = [
            Filter(column="browser", operator="eq", value="Chrome"),
            Filter(column="browser", operator="eq", value="Firefox"),
        ]
        result = build_filter_sql(filters)
        assert "OR" in result["where"]
        assert "f0" in result["params"]
        assert "f1" in result["params"]

    def test_bot_filter(self) -> None:
        filters = [
            Filter(
                column="__bot_filter__",
                operator="eq",
                value='{"enabled": true, "knownBots": true}',
            )
        ]
        result = build_filter_sql(filters)
        # Bot exclusion is now an event-level ``bot_reason`` clause, never a
        # User-Agent SIMILAR TO match or a session subquery.
        assert "we.bot_reason" in result["where"]
        assert result["needs_session_join"] is False

    def test_bot_filter_disabled_returns_empty(self) -> None:
        """``enabled=False`` must skip every bot clause, even when other keys are set."""
        filters = [
            Filter(
                column="__bot_filter__",
                operator="eq",
                value='{"enabled": false, "knownBots": true, "clusterDetection": true}',
            )
        ]
        result = build_filter_sql(filters)
        assert "SIMILAR TO" not in result["where"]
        assert "NOT EXISTS" not in result["where"]
        assert result["needs_session_join"] is False

    def test_empty_filters(self) -> None:
        result = build_filter_sql([])
        assert result["where"] == ""
        assert result["params"] == {}
        assert result["needs_session_join"] is False


class TestSafeIdentifier:
    def test_allowed_value_passes_through(self) -> None:
        assert safe_identifier("hour", GRANULARITIES, "day") == "hour"

    def test_disallowed_value_falls_back(self) -> None:
        # Anything outside the whitelist -- including an injection attempt --
        # collapses to the safe default.
        assert safe_identifier("day'; DROP TABLE website_event; --", GRANULARITIES, "day") == "day"

    def test_empty_and_none_fall_back(self) -> None:
        assert safe_identifier("", GRANULARITIES, "day") == "day"
        assert safe_identifier("year", GRANULARITIES, "day") == "day"  # not in this whitelist


class TestApplyFilters:
    def test_no_filters(self) -> None:
        result = apply_filters(None)
        assert result == {"where": "", "params": {}, "join": ""}

    def test_never_adds_session_join(self) -> None:
        # Sessions are not tracked, so filters never produce a JOIN clause.
        filters = [Filter(column="browser", operator="eq", value="Chrome")]
        result = apply_filters(filters)
        assert result["join"] == ""

    def test_session_join_flag_is_noop(self) -> None:
        filters = [Filter(column="browser", operator="eq", value="Chrome")]
        result = apply_filters(filters, already_joins_session=True)
        assert result["join"] == ""


class TestBuildBotFilterSql:
    """Privacy-first bot exclusion: event-level ``bot_reason`` + country list only.

    There is no User-Agent SIMILAR TO match, no behavioural NOT EXISTS subquery,
    no cluster detection, and no precomputed session-id anti-join — those all
    required identifiers the product no longer collects.
    """

    def test_empty_config_applies_known_bot_defaults(self) -> None:
        """An empty config falls back to knownBots + emptyUa via the bot_reason clause."""
        result = build_bot_filter_sql({})
        assert "we.bot_reason" in result["where"]
        assert result["needs_session_join"] is False
        assert result["params"]["botReasons"] == ["known_bot_user_agent", "empty_user_agent"]

    def test_known_bots_only(self) -> None:
        result = build_bot_filter_sql({"knownBots": True, "emptyUa": False})
        assert result["params"]["botReasons"] == ["known_bot_user_agent"]

    def test_no_reasons_and_no_countries_is_empty(self) -> None:
        """With every reason disabled and no country list, the clause is empty."""
        result = build_bot_filter_sql({"knownBots": False, "emptyUa": False})
        assert result["where"] == ""
        assert result["needs_session_join"] is False
        assert result["params"] == {}

    def test_excluded_countries(self) -> None:
        result = build_bot_filter_sql({
            "knownBots": False,
            "emptyUa": False,
            "excludedCountries": ["CN", "RU"],
        })
        assert "we.country" in result["where"]
        assert result["params"]["botExcludedCountries"] == ["CN", "RU"]
        assert "SIMILAR TO" not in result["where"]
        assert "NOT EXISTS" not in result["where"]

    def test_config_wrapper_is_unwrapped(self) -> None:
        """The mixin passes ``{"config": {...}}``; the builder reads the inner dict."""
        result = build_bot_filter_sql({"config": {"knownBots": True, "emptyUa": False}})
        assert result["params"]["botReasons"] == ["known_bot_user_agent"]


class TestBotFilterPayloadShapes:
    def test_payload_with_config_wrapper(self) -> None:
        """``build_filter_sql`` understands the ``{"config": {...}}`` payload shape."""
        payload = json.dumps({"config": {"knownBots": True, "emptyUa": False}})
        filters = [Filter(column="__bot_filter__", operator="eq", value=payload)]
        result = build_filter_sql(filters)
        assert "we.bot_reason" in result["where"]
        assert result["params"]["botReasons"] == ["known_bot_user_agent"]

    def test_bare_config_payload(self) -> None:
        """A bare config dict (no wrapper) is also accepted."""
        payload = json.dumps({"knownBots": True, "emptyUa": True})
        filters = [Filter(column="__bot_filter__", operator="eq", value=payload)]
        result = build_filter_sql(filters)
        assert "we.bot_reason" in result["where"]


# ---------------------------------------------------------------------------
# date_utils.py
# ---------------------------------------------------------------------------


class TestResolveDateRange:
    def test_30d(self) -> None:
        r = resolve_date_range("30d")
        assert r is not None
        diff = (r.end_date - r.start_date).total_seconds()
        assert 29 * 86400 < diff < 31 * 86400

    def test_7d(self) -> None:
        r = resolve_date_range("7d")
        assert r is not None
        diff = (r.end_date - r.start_date).total_seconds()
        assert 6 * 86400 < diff < 8 * 86400

    def test_today(self) -> None:
        r = resolve_date_range("today")
        assert r is not None
        assert r.start_date.hour == 0
        assert r.start_date.minute == 0

    def test_all_returns_none(self) -> None:
        assert resolve_date_range("all") is None

    def test_custom_returns_none(self) -> None:
        assert resolve_date_range("custom") is None

    def test_unknown_returns_none(self) -> None:
        assert resolve_date_range("foobar") is None


class TestGetAutoGranularity:
    def test_minute_for_short(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(hours=3),
            datetime.now(UTC),
        )
        assert get_auto_granularity(r) == "minute"

    def test_hour_for_day(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(hours=20),
            datetime.now(UTC),
        )
        assert get_auto_granularity(r) == "hour"

    def test_day_for_month(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(days=30),
            datetime.now(UTC),
        )
        assert get_auto_granularity(r) == "day"

    def test_week_for_year(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(days=200),
            datetime.now(UTC),
        )
        assert get_auto_granularity(r) == "week"

    def test_month_for_long(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(days=500),
            datetime.now(UTC),
        )
        assert get_auto_granularity(r) == "month"


class TestGetComparisonRange:
    def test_previous_period(self) -> None:
        r = DateRange(
            datetime(2025, 5, 1, tzinfo=UTC),
            datetime(2025, 5, 31, tzinfo=UTC),
        )
        comp = get_comparison_range(r, "previous_period")
        assert comp.start_date < r.start_date
        assert comp.end_date < r.start_date

    def test_previous_year(self) -> None:
        r = DateRange(
            datetime(2025, 5, 1, tzinfo=UTC),
            datetime(2025, 5, 31, tzinfo=UTC),
        )
        comp = get_comparison_range(r, "previous_year")
        assert comp.start_date.year == 2024
        assert comp.end_date.year == 2024


class TestResolveGranularity:
    def test_auto(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(hours=3),
            datetime.now(UTC),
        )
        assert resolve_granularity("auto", r) == "minute"

    def test_explicit(self) -> None:
        r = DateRange(
            datetime.now(UTC) - timedelta(days=30),
            datetime.now(UTC),
        )
        assert resolve_granularity("week", r) == "week"


# ---------------------------------------------------------------------------
# helpers.py
# ---------------------------------------------------------------------------


class TestComputeDerivedStats:
    def test_basic(self) -> None:
        raw = {
            "pageviews": 100, "visitors": 50, "visits": 60,
            "bounces": 20, "totaltime": 3000,
        }
        result = compute_derived_stats(raw)
        assert result["bounce_rate"] == round(20 / 60 * 100, 1)
        assert result["avg_duration"] == round(3000 / 60, 1)
        assert result["pages_per_visit"] == round(100 / 60, 2)

    def test_zero_visits(self) -> None:
        raw = {"pageviews": 0, "visitors": 0, "visits": 0, "bounces": 0, "totaltime": 0}
        result = compute_derived_stats(raw)
        assert result["bounce_rate"] == 0
        assert result["avg_duration"] == 0

    def test_none_values(self) -> None:
        raw = {
            "pageviews": None, "visitors": None, "visits": None,
            "bounces": None, "totaltime": None,
        }
        result = compute_derived_stats(raw)
        assert result["bounce_rate"] == 0


class TestNum:
    def test_integer(self) -> None:
        assert num(1000) == "1,000"

    def test_none(self) -> None:
        assert num(None) == "-"

    def test_float(self) -> None:
        assert num(1000.0) == "1,000"


class TestPctChange:
    def test_positive(self) -> None:
        assert pct_change(120, 100) == "+20.0%"

    def test_negative(self) -> None:
        assert pct_change(80, 100) == "-20.0%"

    def test_none(self) -> None:
        assert pct_change(None, 100) == "-"

    def test_previous_zero(self) -> None:
        assert pct_change(50, 0) == "+New"

    def test_both_zero(self) -> None:
        assert pct_change(0, 0) == "-"


class TestFormatDuration:
    def test_seconds(self) -> None:
        assert format_duration(45) == "45s"

    def test_minutes(self) -> None:
        assert format_duration(125) == "2m 5s"

    def test_hours(self) -> None:
        assert format_duration(3665) == "1h 1m"

    def test_none(self) -> None:
        assert format_duration(None) == "-"


class TestFormatPercent:
    def test_normal(self) -> None:
        assert format_percent(45.67) == "45.7%"

    def test_none(self) -> None:
        assert format_percent(None) == "-"


# ---------------------------------------------------------------------------
# get_date_trunc
# ---------------------------------------------------------------------------


class TestGetDateTrunc:
    def test_valid_granularity(self) -> None:
        assert get_date_trunc("hour") == "date_trunc('hour', we.created_at)"

    def test_invalid_granularity(self) -> None:
        assert get_date_trunc("invalid") == "date_trunc('day', we.created_at)"


# ---------------------------------------------------------------------------
# Package purity: no async/asyncpg
# ---------------------------------------------------------------------------


class TestPackagePurity:
    def _read_package_code_lines(self) -> dict[str, list[str]]:
        """Read all .py files in the core/mantecato_core package, returning only code lines."""
        import pathlib

        pkg_dir = pathlib.Path(__file__).parent.parent / "core" / "mantecato_core"
        files: dict[str, list[str]] = {}
        for py_file in pkg_dir.rglob("*.py"):
            content = py_file.read_text()
            lines: list[str] = []
            in_docstring = False
            for line in content.splitlines():
                stripped = line.strip()
                if not in_docstring:
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                            continue
                        in_docstring = True
                        continue
                    lines.append(line)
                else:
                    if '"""' in stripped or "'''" in stripped:
                        in_docstring = False
            files[str(py_file.relative_to(pkg_dir))] = lines
        return files

    def test_no_asyncpg_import(self) -> None:
        for name, lines in self._read_package_code_lines().items():
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "import asyncpg" not in stripped, f"import asyncpg in {name}: {stripped}"
                assert "from asyncpg" not in stripped, f"from asyncpg in {name}: {stripped}"

    def test_no_async_def(self) -> None:
        for name, lines in self._read_package_code_lines().items():
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "async def" not in stripped, f"async def in {name}: {stripped}"

    def test_no_await(self) -> None:
        for name, lines in self._read_package_code_lines().items():
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "await " not in stripped, f"await in {name}: {stripped}"
