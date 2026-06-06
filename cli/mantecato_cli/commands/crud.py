"""CRUD CLI commands — dashboards, API keys, bot config, scheduled exports.

Every command body follows the same pattern:

1. :func:`bootstrap` Django settings (lazy via :func:`cli.mantecato_cli.app.bootstrap`).
2. Import the service function inside the command body so the test suite
   can monkeypatch ``apps.<app>.services.<fn>`` without import-time cost.
3. Call the service and :func:`emit` the result.
4. For detail/delete commands, route through :func:`get_or_die` so the
   "not found" branch is one line instead of three.
"""

from __future__ import annotations

import typer

from cli.mantecato_cli.app import (
    FORMAT_OPTION,
    USER_OPT,
    WEBSITE_OPT,
    app,
    bootstrap,
    emit,
    get_or_die,
)

# Smaller option templates reused only inside this module.
_REPORT_ID_ARG = typer.Argument(..., help="Report UUID")
_NAME_OPT = typer.Option(..., "--name", "-n")


# ============================================================================
# Detail lookups (single object by id)
# ============================================================================


@app.command("dashboard")
def dashboard_detail_cmd(
    report_id: str = _REPORT_ID_ARG,
    user_id: str = USER_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Get one dashboard."""
    bootstrap()
    from apps.dashboards.services import get_dashboard_detail

    emit(
        get_or_die(get_dashboard_detail(report_id, user_id), "Dashboard not found."),
        format,
    )


@app.command("scheduled-exports")
def scheduled_exports_cmd(user_id: str = USER_OPT, format: str = FORMAT_OPTION) -> None:
    """List scheduled exports for a user."""
    bootstrap()
    from apps.settings_app.services import get_scheduled_exports_for_user

    emit(get_scheduled_exports_for_user(user_id), format)


@app.command("scheduled-export")
def scheduled_export_cmd(
    report_id: str = _REPORT_ID_ARG,
    user_id: str = USER_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Get one scheduled export."""
    bootstrap()
    from apps.settings_app.services import get_scheduled_export_detail

    emit(
        get_or_die(
            get_scheduled_export_detail(report_id, user_id), "Scheduled export not found."
        ),
        format,
    )


@app.command("scheduled-export-delete")
def scheduled_export_delete_cmd(
    report_id: str = _REPORT_ID_ARG,
    user_id: str = USER_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Delete a scheduled export."""
    bootstrap()
    from apps.settings_app.services import remove_scheduled_export

    get_or_die(remove_scheduled_export(report_id, user_id), "Scheduled export not found.")
    emit({"deleted": True}, format)


# ============================================================================
# Dashboards
# ============================================================================


@app.command("dashboards")
def dashboards_list(user_id: str = USER_OPT, format: str = FORMAT_OPTION) -> None:
    """List dashboards for a user."""
    bootstrap()
    from apps.dashboards.services import get_dashboards_for_user

    emit(get_dashboards_for_user(user_id), format)


@app.command("dashboard-create")
def dashboard_create_cmd(
    user_id: str = USER_OPT,
    website_id: str = WEBSITE_OPT,
    name: str = _NAME_OPT,
    description: str = typer.Option("", "--description", "-d"),
    format: str = FORMAT_OPTION,
) -> None:
    """Create a new dashboard."""
    bootstrap()
    from apps.dashboards.services import create_new_dashboard

    emit(create_new_dashboard(user_id, website_id, name, description=description), format)


@app.command("dashboard-delete")
def dashboard_delete_cmd(
    report_id: str = _REPORT_ID_ARG,
    user_id: str = USER_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Delete a dashboard."""
    bootstrap()
    from apps.dashboards.services import remove_dashboard

    get_or_die(remove_dashboard(report_id, user_id), "Dashboard not found.")
    emit({"deleted": True}, format)


# ============================================================================
# API Keys
# ============================================================================


@app.command("api-keys")
def api_keys_list(user_id: str = USER_OPT, format: str = FORMAT_OPTION) -> None:
    """List API keys for a user."""
    bootstrap()
    from apps.settings_app.services import get_api_keys_for_user

    emit(get_api_keys_for_user(user_id), format)


@app.command("api-key-create")
def api_key_create_cmd(
    user_id: str = USER_OPT,
    name: str = _NAME_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Generate a new API key (raw key is shown once in the output)."""
    bootstrap()
    from apps.settings_app.services import generate_new_api_key

    emit(generate_new_api_key(user_id, name), format)


@app.command("api-key-delete")
def api_key_delete_cmd(
    key_id: str = typer.Argument(..., help="API key UUID"),
    user_id: str = USER_OPT,
    format: str = FORMAT_OPTION,
) -> None:
    """Revoke an API key."""
    bootstrap()
    from apps.settings_app.services import remove_api_key

    get_or_die(remove_api_key(key_id, user_id), "API key not found.")
    emit({"deleted": True}, format)


# ============================================================================
# Bot Config
# ============================================================================


@app.command("bot-config")
def bot_config_get_cmd(website: str = WEBSITE_OPT, format: str = FORMAT_OPTION) -> None:
    """Read the bot-detection config for a website."""
    bootstrap()
    from apps.settings_app.services import get_bot_config

    emit(get_bot_config(website), format)

