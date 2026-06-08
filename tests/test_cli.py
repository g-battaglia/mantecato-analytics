"""Tests for the Mantecato Typer CLI.

Covers:
- django.setup() bootstrap is invoked
- Commands call service/query functions directly (no network)
- Output formats: json, table, csv
- Error handling for invalid params
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.mantecato_cli.main import app

runner = CliRunner()

_USER_ID = "a0000000-0000-0000-0000-000000000001"
_WEBSITE_ID = "b0000000-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


class TestBootstrap:
    def test_setup_django_callable(self) -> None:
        from cli.mantecato_cli.bootstrap import setup_django

        assert callable(setup_django)

    def test_sets_settings_module(self) -> None:
        import os

        with patch.dict(os.environ, {}, clear=False):
            from cli.mantecato_cli.bootstrap import setup_django

            os.environ.pop("DJANGO_SETTINGS_MODULE", None)
            setup_django()
            assert os.environ.get("DJANGO_SETTINGS_MODULE") == "mantecato.settings"


# ---------------------------------------------------------------------------
# Sites command — patch at the service module level
# ---------------------------------------------------------------------------


class TestSitesCommand:
    @patch("apps.analytics.services.resolve_websites_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_sites_json_output(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = [
            {"id": _WEBSITE_ID, "name": "Test", "domain": "example.com"},
        ]
        result = runner.invoke(app, ["sites", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "Test"

    @patch("apps.analytics.services.resolve_websites_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_sites_table_output(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = [
            {"id": _WEBSITE_ID, "name": "Test", "domain": "example.com"},
        ]
        result = runner.invoke(app, ["sites", "--format", "table"])
        assert result.exit_code == 0
        assert "Test" in result.output
        assert "example.com" in result.output

    @patch("apps.analytics.services.resolve_websites_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_sites_csv_output(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = [
            {"id": _WEBSITE_ID, "name": "Test", "domain": "example.com"},
        ]
        result = runner.invoke(app, ["sites", "--format", "csv"])
        assert result.exit_code == 0
        assert "Test" in result.output
        assert "name" in result.output


# ---------------------------------------------------------------------------
# Analytics commands
# ---------------------------------------------------------------------------


class TestOverviewCommand:
    @patch("apps.analytics.services.get_overview_data")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_overview_json(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_overview: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_overview.return_value = {"stats": {"pageviews": 100}}

        result = runner.invoke(
            app,
            [
                "overview",
                "--website",
                _WEBSITE_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["stats"]["pageviews"] == 100

    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_overview_invalid_range(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = None
        result = runner.invoke(
            app,
            [
                "overview",
                "--website",
                _WEBSITE_ID,
                "--range",
                "all",
            ],
        )
        assert result.exit_code == 1


class TestPagesCommand:
    @patch("apps.analytics.services.get_pages_data")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_pages_json(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_pages: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_pages.return_value = {"pages": [{"url": "/home", "views": 50}], "page": 1}

        result = runner.invoke(
            app,
            [
                "pages",
                "--website",
                _WEBSITE_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["pages"]) == 1


class TestRealtimeCommand:
    @patch("apps.analytics.services.get_realtime_data")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_realtime(
        self,
        mock_setup: MagicMock,
        mock_realtime: MagicMock,
    ) -> None:
        mock_realtime.return_value = {"active": 7, "recent_events": [], "current_pages": []}

        result = runner.invoke(
            app,
            [
                "realtime",
                "--website",
                _WEBSITE_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == 7


class TestDevicesCommand:
    @patch("apps.analytics.services.get_devices_data")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_devices_table(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_devices: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_devices.return_value = {
            "browser": [{"value": "Chrome", "visitors": 80}],
            "os": [],
            "device": [],
            "screen": [],
            "language": [],
        }

        result = runner.invoke(
            app,
            [
                "devices",
                "--website",
                _WEBSITE_ID,
                "--format",
                "table",
            ],
        )
        assert result.exit_code == 0


class TestGeoCommand:
    @patch("apps.analytics.services.get_geo_data")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_geo_country_level(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_geo: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_geo.return_value = {"geo": [], "level": "country"}

        result = runner.invoke(
            app,
            [
                "geo",
                "--website",
                _WEBSITE_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0


class TestExpandedQueryCommands:
    def test_cli_exposes_at_least_26_commands(self) -> None:
        assert len(app.registered_commands) >= 26

    @patch("core.mantecato_core.queries.stats.get_website_stats")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_stats_command(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_stats: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_stats.return_value = {
            "pageviews": 10,
            "visitors": 5,
            "visits": 6,
            "bounces": 1,
            "totaltime": 120,
        }

        result = runner.invoke(
            app,
            [
                "stats",
                "--website",
                _WEBSITE_ID,
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["pageviews"] == 10
        assert data["avg_duration"] == 20

    @patch("core.mantecato_core.queries.filter_values.get_filter_values")
    @patch("core.mantecato_core.date_utils.resolve_date_range")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_filter_values_command(
        self,
        mock_setup: MagicMock,
        mock_resolve: MagicMock,
        mock_values: MagicMock,
    ) -> None:
        mock_resolve.return_value = MagicMock()
        mock_values.return_value = ["Chrome", "Safari"]

        result = runner.invoke(
            app,
            [
                "filter-values",
                "--website",
                _WEBSITE_ID,
                "--column",
                "browser",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == [{"value": "Chrome"}, {"value": "Safari"}]

    @patch("apps.settings_app.services.get_scheduled_exports_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_scheduled_exports_command(
        self,
        mock_setup: MagicMock,
        mock_exports: MagicMock,
    ) -> None:
        mock_exports.return_value = [{"id": "exp1", "name": "Weekly"}]

        result = runner.invoke(
            app,
            [
                "scheduled-exports",
                "--user",
                _USER_ID,
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "Weekly"


# ---------------------------------------------------------------------------
# CRUD commands
# ---------------------------------------------------------------------------


class TestDashboardCommands:
    @patch("apps.dashboards.services.get_dashboards_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_list_dashboards(
        self,
        mock_setup: MagicMock,
        mock_list: MagicMock,
    ) -> None:
        mock_list.return_value = [{"id": "abc", "name": "Main"}]
        result = runner.invoke(
            app,
            [
                "dashboards",
                "--user",
                _USER_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

    @patch("apps.dashboards.services.create_new_dashboard")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_create_dashboard(
        self,
        mock_setup: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_create.return_value = {"id": "new", "name": "My Dash"}
        result = runner.invoke(
            app,
            [
                "dashboard-create",
                "--user",
                _USER_ID,
                "--website",
                _WEBSITE_ID,
                "--name",
                "My Dash",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "My Dash"

    @patch("apps.dashboards.services.remove_dashboard")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_delete_dashboard(
        self,
        mock_setup: MagicMock,
        mock_remove: MagicMock,
    ) -> None:
        mock_remove.return_value = True
        result = runner.invoke(
            app,
            [
                "dashboard-delete",
                "c0000000-0000-0000-0000-000000000003",
                "--user",
                _USER_ID,
            ],
        )
        assert result.exit_code == 0


class TestApiKeyCommands:
    @patch("apps.settings_app.services.get_api_keys_for_user")
    @patch("cli.mantecato_cli.main.setup_django")
    def test_list_api_keys(
        self,
        mock_setup: MagicMock,
        mock_list: MagicMock,
    ) -> None:
        mock_list.return_value = [{"id": "k1", "name": "cli-key"}]
        result = runner.invoke(
            app,
            [
                "api-keys",
                "--user",
                _USER_ID,
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Output format helpers
# ---------------------------------------------------------------------------


class TestFormatOutput:
    def test_json_format(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output([{"a": 1}], "json")
        parsed = json.loads(result)
        assert parsed == [{"a": 1}]

    def test_table_format(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output([{"name": "Alice", "age": "30"}], "table")
        assert "Alice" in result
        assert "name" in result

    def test_csv_format(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output([{"name": "Bob", "age": "25"}], "csv")
        assert "name,age" in result
        assert "Bob,25" in result

    def test_table_empty_list(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output([], "table")
        # Empty list falls through to str() conversion
        assert result == "[]"

    def test_csv_dict_input(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output({"key": "value"}, "csv")
        assert "key" in result

    def test_table_dict_input(self) -> None:
        from cli.mantecato_cli.helpers import format_output

        result = format_output({"key": "value"}, "table")
        assert "key" in result


# ---------------------------------------------------------------------------
# Command no-args help
# ---------------------------------------------------------------------------


class TestAppHelp:
    def test_no_args_returns_usage_error(self) -> None:
        result = runner.invoke(app, [])
        # Typer returns exit code 2 when no_args_is_help=True
        assert result.exit_code == 2
        assert "Usage" in result.output

    def test_help_flag(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "sites" in result.output
        assert "overview" in result.output
