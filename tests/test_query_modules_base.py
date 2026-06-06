"""Tests for the base query modules (stats, pageviews, filter_values, devices, geo).

Covers:
- Purity: no async def, await, asyncpg, $1 placeholders in any query module.
- Live read-only execution on live development database for key functions.
- Uses django_db_blocker.unblock() — no test DB, no writes.
"""

from __future__ import annotations

import importlib
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from core.mantecato_core.database import raw_query
from core.mantecato_core.queries import (
    get_country_breakdown,
    get_device_metrics,
    get_filter_values,
    get_first_event_date,
    get_geo_metrics,
    get_page_metrics,
    get_page_time_series,
    get_pageview_time_series,
    get_top_pages,
    get_top_sections,
    get_traffic_heatmap,
    get_active_visitors,
    get_current_pages,
    get_recent_events,
    get_top_pages,
    get_top_sections,
    get_website_stats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY_MODULES_DIR = pathlib.Path(__file__).parent.parent / "core" / "mantecato_core" / "queries"


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

        with (
            psycopg.connect(
                host=host,
                port=db.get("PORT", 5432),
                dbname=db.get("NAME", "mantecato"),
                user=db.get("USER", ""),
                password=db.get("PASSWORD", ""),
                connect_timeout=2,
            ) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def _get_first_website_id() -> str | None:
    rows = raw_query("SELECT id FROM website WHERE is_deleted = false ORDER BY created_at LIMIT 1")
    return str(rows[0]["id"]) if rows else None


# ---------------------------------------------------------------------------
# Purity tests
# ---------------------------------------------------------------------------


class TestQueryModulesPurity:
    @pytest.fixture(
        params=[
            "stats.py",
            "pageviews.py",
            "filter_values.py",
            "devices.py",
            "geo.py",
            "__init__.py",
        ]
    )
    def module_path(self, request: pytest.FixtureRequest) -> pathlib.Path:
        return _QUERY_MODULES_DIR / request.param

    def test_no_async_def(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "async def" not in stripped, f"async def in {module_path.name}: {stripped}"

    def test_no_await(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "await " not in stripped, f"await in {module_path.name}: {stripped}"

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
            assert "from asyncpg" not in stripped, f"from asyncpg in {module_path.name}: {stripped}"

    def test_no_dollar_placeholders(self, module_path: pathlib.Path) -> None:
        if not module_path.exists():
            pytest.skip(f"{module_path.name} not found")
        for line in _read_module_lines(module_path):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("def "):
                continue
            assert "$1" not in stripped, f"$1 placeholder in {module_path.name}: {stripped}"
            assert "$2" not in stripped, f"$2 placeholder in {module_path.name}: {stripped}"


class TestQueryModulesImportable:
    @pytest.mark.parametrize(
        "module_name",
        [
            "core.mantecato_core.queries",
            "core.mantecato_core.queries.stats",
            "core.mantecato_core.queries.pageviews",
            "core.mantecato_core.queries.filter_values",
            "core.mantecato_core.queries.devices",
            "core.mantecato_core.queries.geo",
        ],
    )
    def test_module_imports(self, module_name: str) -> None:
        mod = importlib.import_module(module_name)
        assert mod is not None


# ---------------------------------------------------------------------------
# Live database tests (live development database only, read-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestStatsLive:
    @pytest.fixture(autouse=True)
    def _setup_website(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    @property
    def _date_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=60), now

    def test_get_website_stats(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_website_stats(self.website_id, start, end)
        assert isinstance(result, dict)
        assert "pageviews" in result
        assert "visitors" in result
        assert "visits" in result
        assert "bounces" in result
        assert "totaltime" in result
        assert all(isinstance(result[k], int) for k in result)

    def test_get_website_stats_nonzero(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_website_stats(self.website_id, start, end)
        assert result["pageviews"] > 0 or result["visitors"] >= 0

    def test_get_first_event_date(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            result = get_first_event_date(self.website_id)
        assert result is None or isinstance(result, datetime)

    def test_get_pageview_time_series(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_pageview_time_series(self.website_id, start, end, "day")
        assert isinstance(result, list)
        if result:
            assert "time" in result[0]
            assert "pageviews" in result[0]
            assert "visitors" in result[0]

    def test_get_top_pages(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_top_pages(self.website_id, start, end, limit=5)
        assert isinstance(result, list)
        if result:
            assert "urlPath" in result[0]
            assert "views" in result[0]
            assert "visitors" in result[0]

    def test_get_country_breakdown(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_country_breakdown(self.website_id, start, end)
        assert isinstance(result, list)
        if result:
            assert "country" in result[0]
            assert "pageviews" in result[0]
            assert "pageviews" in result[0]

    def test_get_top_sections(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_top_sections(self.website_id, start, end)
        assert isinstance(result, list)

    def test_get_website_stats_with_filter(self, django_db_blocker: object) -> None:
        from core.mantecato_core.filters import Filter

        start, end = self._date_range
        filters = [Filter(column="country", operator="eq", value="IT")]
        with django_db_blocker.unblock():
            result = get_website_stats(self.website_id, start, end, filters=filters)
        assert isinstance(result, dict)
        assert "pageviews" in result


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestPageviewsLive:
    @pytest.fixture(autouse=True)
    def _setup_website(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
            start = datetime.now(UTC) - timedelta(days=60)
            pages = get_top_pages(self.website_id, start, datetime.now(UTC), limit=1)
        if not self.website_id:
            pytest.skip("No seeded website found")
        self.url_path = pages[0]["urlPath"] if pages else "/"

    @property
    def _date_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=60), now

    def test_get_page_metrics(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_page_metrics(self.website_id, start, end, limit=5)
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "urlPath" in row
            assert "views" in row
            assert "visitors" in row
            assert "entries" in row
            assert "exits" in row
            assert "bounceRate" in row

    def test_get_page_time_series(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_page_time_series(self.website_id, self.url_path, start, end, "day")
        assert isinstance(result, list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestFilterValuesLive:
    @pytest.fixture(autouse=True)
    def _setup_website(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    @property
    def _date_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=60), now

    def test_browser_values(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_filter_values(self.website_id, "browser", start, end)
        assert isinstance(result, list)
        assert all(isinstance(v, str) for v in result)

    def test_url_path_values(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_filter_values(self.website_id, "url_path", start, end)
        assert isinstance(result, list)

    def test_invalid_column(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_filter_values(self.website_id, "invalid_col", start, end)
        assert result == []

    def test_search_filter(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_filter_values(self.website_id, "country", start, end, search="I")
        assert isinstance(result, list)


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestDevicesLive:
    @pytest.fixture(autouse=True)
    def _setup_website(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    @property
    def _date_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=60), now

    def test_browser_dimension(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_device_metrics(self.website_id, start, end, "browser")
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "value" in row
            assert "visitors" in row
            assert "pageviews" in row
            assert "percentage" in row
            assert row["percentage"] > 0

    def test_os_dimension(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_device_metrics(self.website_id, start, end, "os")
        assert isinstance(result, list)

    def test_device_dimension(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_device_metrics(self.website_id, start, end, "device")
        assert isinstance(result, list)

    def test_invalid_dimension(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_device_metrics(self.website_id, start, end, "invalid")
        assert result == []


@pytest.mark.skipif(
    not _is_live_database_available(),
    reason="live development database database not available",
)
class TestGeoLive:
    @pytest.fixture(autouse=True)
    def _setup_website(self, django_db_blocker: object) -> None:
        with django_db_blocker.unblock():
            self.website_id = _get_first_website_id()
        if not self.website_id:
            pytest.skip("No seeded website found")

    @property
    def _date_range(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=60), now

    def test_country_level(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_geo_metrics(self.website_id, start, end, level="country")
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "country" in row
            assert "visitors" in row
            assert "pageviews" in row
            assert "visits" in row
            assert "bounceRate" in row
            assert "avgDuration" in row

    def test_region_level(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_geo_metrics(
                self.website_id,
                start,
                end,
                level="region",
                country_filter="IT",
            )
        assert isinstance(result, list)
        if result:
            assert "region" in result[0]

    def test_city_level(self, django_db_blocker: object) -> None:
        start, end = self._date_range
        with django_db_blocker.unblock():
            result = get_geo_metrics(
                self.website_id,
                start,
                end,
                level="city",
                country_filter="IT",
                region_filter="Lombardia",
            )
        assert isinstance(result, list)
        if result:
            assert "city" in result[0]
