"""Tests for the analytics query modules (T5b batch).

Modules covered: sources, sessions, events, compare, realtime, heatmap,
retention, funnels, journeys, revenue, engagement.

Covers:
- Purity: no async def, await, asyncpg, $1/$2 placeholders.
- Import: every module is importable, every public function exists.
- Live read-only smoke tests on live development database for key functions per module.
- Uses django_db_blocker.unblock() — no test DB, no writes.
"""

from __future__ import annotations

import importlib
import pathlib
import re
from datetime import UTC, datetime, timedelta

import pytest

from core.mantecato_core.database import raw_query

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY_MODULES_DIR = (
    pathlib.Path(__file__).parent.parent / "core" / "mantecato_core" / "queries"
)

ANALYTICS_MODULES = [
    "sources.py",
    "sessions.py",
    "events.py",
    "compare.py",
    "realtime.py",
    "heatmap.py",
    "retention.py",
    "funnels.py",
    "journeys.py",
    "revenue.py",
    "engagement.py",
]


def _read_module_lines(path: pathlib.Path) -> list[str]:
    content = path.read_text()
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
    return lines


def _is_live_database_available() -> bool:
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


def _get_first_website_id() -> str | None:
    rows = raw_query(
        "SELECT id FROM website WHERE is_deleted = false ORDER BY created_at LIMIT 1"
    )
    return str(rows[0]["id"]) if rows else None


# ---------------------------------------------------------------------------
# Purity tests — all 11 new modules
# ---------------------------------------------------------------------------


class TestAnalyticsModulesPurity:
    @pytest.fixture(params=ANALYTICS_MODULES)
    def module_path(self, request: pytest.FixtureRequest) -> pathlib.Path:
        return _QUERY_MODULES_DIR / request.param

    def test_no_async_def(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "async def" not in stripped, (
                f"async def in {module_path.name}: {stripped}"
            )

    def test_no_await(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "await " not in stripped, (
                f"await in {module_path.name}: {stripped}"
            )

    def test_no_asyncpg_import(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "import asyncpg" not in stripped, (
                f"import asyncpg in {module_path.name}: {stripped}"
            )
            assert "from asyncpg" not in stripped, (
                f"from asyncpg in {module_path.name}: {stripped}"
            )

    def test_no_dollar_placeholders(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("def "):
                continue
            assert "$1" not in stripped, (
                f"$1 placeholder in {module_path.name}: {stripped}"
            )
            assert "$2" not in stripped, (
                f"$2 placeholder in {module_path.name}: {stripped}"
            )

    def test_no_asyncio_import(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "import asyncio" not in stripped, (
                f"import asyncio in {module_path.name}: {stripped}"
            )


# ---------------------------------------------------------------------------
# Import tests — every module
# ---------------------------------------------------------------------------


class TestAnalyticsModulesImportable:
    @pytest.mark.parametrize("module_name", [
        "core.mantecato_core.queries.sources",
        "core.mantecato_core.queries.sessions",
        "core.mantecato_core.queries.events",
        "core.mantecato_core.queries.compare",
        "core.mantecato_core.queries.realtime",
        "core.mantecato_core.queries.heatmap",
        "core.mantecato_core.queries.retention",
        "core.mantecato_core.queries.funnels",
        "core.mantecato_core.queries.journeys",
        "core.mantecato_core.queries.revenue",
        "core.mantecato_core.queries.engagement",
    ])
    def test_module_imports(self, module_name: str) -> None:
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_init_exports_all_functions(self) -> None:
        import core.mantecato_core.queries as q

        for name in q.__all__:
            assert hasattr(q, name), f"Missing export: {name}"
            assert callable(getattr(q, name)), f"Not callable: {name}"


# ---------------------------------------------------------------------------
# SQL shape tests — every public function has a query with {{placeholders}}
# ---------------------------------------------------------------------------


class TestSqlShape:
    """Verify converted modules use raw_query and {{name}} / {{name::type}} placeholders."""

    @pytest.mark.parametrize("module_file", ANALYTICS_MODULES)
    def test_uses_curly_brace_placeholders(self, module_file: str) -> None:
        path = _QUERY_MODULES_DIR / module_file
        if not path.exists():
            pytest.skip(f"{module_file} not found")
        content = path.read_text()

        assert "raw_query" in content, (
            f"Module {module_file} does not reference raw_query"
        )

        placeholders = re.findall(r"\{\{[^}]+\}\}", content)
        if not placeholders:
            return

        for placeholder in placeholders:
            assert re.match(
                r"^\{\{\s*\w+(\s*::\s*[\w\[\]]+)?\s*\}\}$", placeholder
            ), f"Invalid SQL placeholder {placeholder!r} in {module_file}"

    @pytest.mark.parametrize("module_file", ANALYTICS_MODULES)
    def test_no_old_mantecato_core_import(self, module_file: str) -> None:
        path = _QUERY_MODULES_DIR / module_file
        if not path.exists():
            pytest.skip(f"{module_file} not found")
        content = path.read_text()
        assert "from mantecato_core." not in content, (
            f"Old import path in {module_file}"
        )


# ---------------------------------------------------------------------------
# Live database smoke tests (live development database only, read-only)
# ---------------------------------------------------------------------------

_DATE_RANGE: tuple[datetime, datetime] = (
    datetime.now(UTC) - timedelta(days=60),
    datetime.now(UTC),
)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestSourcesLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_referrer_metrics(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.sources import get_referrer_metrics
            result = get_referrer_metrics(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "referrerDomain" in r
            assert "visitors" in r
            assert "pageviews" in r
            assert "bounceRate" in r
            assert "avgDuration" in r

    def test_get_channel_metrics(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.sources import get_channel_metrics
            result = get_channel_metrics(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_utm_metrics(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.sources import get_utm_metrics
            result = get_utm_metrics(self.website_id, start, end, group_by="utm_source")
        assert isinstance(result, list)

    def test_get_hostname_metrics(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.sources import get_hostname_metrics
            result = get_hostname_metrics(self.website_id, start, end)
        assert isinstance(result, list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestSessionsLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_session_list(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.sessions import get_session_list
            result = get_session_list(self.website_id, start, end, limit=5)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "sessionId" in r
            assert "country" in r
            assert "browser" in r
            assert "pagesViewed" in r
            assert "duration" in r
            assert "startedAt" in r


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestEventsLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_event_metrics(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.events import get_event_metrics
            result = get_event_metrics(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "eventName" in r
            assert "count" in r
            assert "visitors" in r
            assert "lastTriggered" in r

    def test_event_time_series_multi_matches_loop(self, django_db_blocker: object) -> None:
        """The combined multi-event query must equal the per-event loop, byte for byte."""
        import json

        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.events import (
                get_event_metrics,
                get_event_time_series,
                get_event_time_series_multi,
            )

            top = get_event_metrics(self.website_id, start, end, limit=5)
            names = [e["eventName"] for e in top]
            multi = get_event_time_series_multi(self.website_id, names, start, end, "day")
            loop = {
                n: get_event_time_series(self.website_id, n, start, end, "day") for n in names
            }
        for n in names:
            assert json.dumps(multi.get(n, []), default=str) == json.dumps(loop[n], default=str)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestStatsComparisonLive:
    """The combined current+previous helpers must equal two separate calls."""

    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_website_stats_comparison_matches_separate(self, django_db_blocker: object) -> None:
        import json

        now = datetime.now(UTC)
        cur_s, prev_s = now - timedelta(days=7), now - timedelta(days=14)
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.stats import (
                get_website_stats,
                get_website_stats_comparison,
            )

            combined = get_website_stats_comparison(self.website_id, cur_s, now, prev_s, cur_s)
            separate = {
                "current": get_website_stats(self.website_id, cur_s, now),
                "previous": get_website_stats(self.website_id, prev_s, cur_s),
            }
        assert json.dumps(combined, sort_keys=True, default=str) == json.dumps(
            separate, sort_keys=True, default=str
        )

    def test_pageview_ts_comparison_matches_separate(self, django_db_blocker: object) -> None:
        import json

        now = datetime.now(UTC)
        cur_s, prev_s = now - timedelta(days=7), now - timedelta(days=14)
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.stats import (
                get_pageview_time_series,
                get_pageview_time_series_comparison,
            )

            combined = get_pageview_time_series_comparison(
                self.website_id, cur_s, now, prev_s, cur_s, "day"
            )
            separate = {
                "current": get_pageview_time_series(self.website_id, cur_s, now, "day"),
                "previous": get_pageview_time_series(self.website_id, prev_s, cur_s, "day"),
            }
        assert json.dumps(combined, sort_keys=True, default=str) == json.dumps(
            separate, sort_keys=True, default=str
        )


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestCompareLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_comparison_stats(self, django_db_blocker: object) -> None:
        now = datetime.now(UTC)
        current_start = now - timedelta(days=7)
        previous_start = now - timedelta(days=14)
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.compare import get_comparison_stats
            result = get_comparison_stats(
                self.website_id,
                current_start=current_start,
                current_end=now,
                previous_start=previous_start,
                previous_end=current_start,
            )
        assert isinstance(result, list)
        assert len(result) == 2
        periods = {r["period"] for r in result}
        assert "current" in periods
        assert "previous" in periods
        for r in result:
            assert "pageviews" in r
            assert "visitors" in r
            assert "visits" in r
            assert "bounces" in r
            assert "totaltime" in r


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestRealtimeLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_active_visitors(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.realtime import get_active_visitors
            result = get_active_visitors(self.website_id)
        assert isinstance(result, dict)
        assert "count" in result
        assert "visitors" in result
        assert isinstance(result["visitors"], list)

    def test_get_current_pages(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.realtime import get_current_pages
            result = get_current_pages(self.website_id)
        assert isinstance(result, list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestHeatmapLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_traffic_heatmap(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.heatmap import get_traffic_heatmap
            result = get_traffic_heatmap(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "dayOfWeek" in r
            assert "hour" in r
            assert "pageviews" in r
            assert "visitors" in r
            assert 0 <= r["dayOfWeek"] <= 6
            assert 0 <= r["hour"] <= 23


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestRetentionLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_retention(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.retention import get_retention
            result = get_retention(self.website_id, start, end, granularity="week")
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "cohort" in r
            assert "cohortSize" in r
            assert "periods" in r
            assert isinstance(r["periods"], list)
            assert len(r["periods"]) == 13


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestFunnelsLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_funnel_with_two_steps(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        steps = [
            {"type": "url", "value": "/"},
            {"type": "url", "value": "/docs"},
        ]
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.funnels import get_funnel
            result = get_funnel(self.website_id, start, end, steps)
        assert isinstance(result, list)
        assert len(result) == 2
        for r in result:
            assert "step" in r
            assert "label" in r
            assert "visitors" in r
            assert "dropoff" in r
            assert "conversionRate" in r

    def test_get_funnel_too_few_steps(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.funnels import get_funnel
            result = get_funnel(self.website_id, start, end, [{"type": "url", "value": "/"}])
        assert result == []


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestJourneysLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_journeys(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.journeys import get_journeys
            result = get_journeys(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "path" in r
            assert "count" in r
            assert "percentage" in r
            assert isinstance(r["path"], list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestRevenueLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_revenue_summary(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.revenue import get_revenue_summary
            result = get_revenue_summary(self.website_id, start, end)
        assert isinstance(result, dict)
        assert "totalRevenue" in result
        assert "transactions" in result
        assert "uniqueCustomers" in result
        assert "arpu" in result

    def test_get_revenue_time_series(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.revenue import get_revenue_time_series
            result = get_revenue_time_series(self.website_id, start, end, "day")
        assert isinstance(result, list)

    def test_get_revenue_by_event(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.revenue import get_revenue_by_event
            result = get_revenue_by_event(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_revenue_by_country(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.revenue import get_revenue_by_country
            result = get_revenue_by_country(self.website_id, start, end)
        assert isinstance(result, list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestEngagementLive:
    @pytest.fixture(autouse=True)
    def _setup(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    def test_get_duration_distribution(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_duration_distribution
            result = get_duration_distribution(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            r = result[0]
            assert "bucket" in r
            assert "bucketOrder" in r
            assert "visits" in r
            assert "percentage" in r

    def test_get_duration_percentiles(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_duration_percentiles
            result = get_duration_percentiles(self.website_id, start, end)
        assert isinstance(result, dict)
        expected_keys = (
            "p50", "p75", "p90", "p95", "p99",
            "avg", "median", "min", "max", "totalVisits",
        )
        for key in expected_keys:
            assert key in result

    def test_get_duration_by_page(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_duration_by_page
            result = get_duration_by_page(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_bounce_rate_by_page(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_bounce_rate_by_page
            result = get_bounce_rate_by_page(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_bounce_rate_by_source(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_bounce_rate_by_source
            result = get_bounce_rate_by_source(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_sessions_for_bucket_invalid(self, django_db_blocker: object) -> None:
        start, end = _DATE_RANGE
        with django_db_blocker.unblock():
            from core.mantecato_core.queries.engagement import get_sessions_for_bucket
            result = get_sessions_for_bucket(
                self.website_id, start, end, bucket="nonexistent"
            )
        assert result["sessions"] == []
        assert result["total"] == 0
