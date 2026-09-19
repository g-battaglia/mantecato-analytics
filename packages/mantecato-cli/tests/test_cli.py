from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003  pytest fixture annotation
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from mantecato_cli._http import ApiTransport
from mantecato_cli.config import ClientConfig, UserConfig, load_user_config
from mantecato_cli.errors import ApiError, UsageError
from mantecato_cli.main import app
from mantecato_cli.output import render

runner = CliRunner()


def test_empty_csv_keeps_a_stable_header() -> None:
    result = render(
        {
            "query": {"dimensions": ["country"], "metrics": ["pageviews"]},
            "rows": [],
        },
        "csv",
    )
    assert result == "country,pageviews"


def test_help_and_schema_need_no_credentials() -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["schema", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["schema_version"] == "1"


def test_transport_sends_bearer_and_refuses_redirect() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["Authorization"]
        return httpx.Response(302, headers={"Location": "https://other.example/api"})

    client = ApiTransport(
        ClientConfig("https://analytics.example", "mtk_secret"),
        transport=httpx.MockTransport(handler),
    )
    try:
        client.get("/api/sites/")
    except ApiError as exc:
        assert exc.code == "REDIRECT_REFUSED"
    else:  # pragma: no cover
        raise AssertionError("redirect was followed")
    assert seen["authorization"] == "Bearer mtk_secret"


def test_plain_http_is_limited_to_loopback(monkeypatch) -> None:
    monkeypatch.setenv("MANTECATO_URL", "http://analytics.example")
    monkeypatch.setenv("MANTECATO_API_KEY", "mtk_secret")
    from mantecato_cli.config import resolve_client_config

    try:
        resolve_client_config(url=None, key_file=None, profile=None, config_path=None, timeout=1)
    except UsageError as exc:
        assert "loopback" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("remote plain HTTP was accepted")


def test_config_rejects_executable_or_extra_segment_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("segments:\n  bad:\n    filters: []\n    command: rm -rf /\n")
    try:
        load_user_config(path)
    except UsageError as exc:
        assert "only a filters array" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsafe segment field was accepted")


@patch("mantecato_cli.main.AppState.connect")
def test_sites_uses_remote_api(mock_connect: MagicMock) -> None:
    api = MagicMock()
    api.get.return_value = {"websites": [{"id": "site-1", "name": "Site"}]}
    mock_connect.return_value = (api, UserConfig(profiles={}, segments={}))
    result = runner.invoke(app, ["sites", "--format", "json"])
    assert result.exit_code == 0
    api.get.assert_called_once_with("/api/sites/")
    assert json.loads(result.output)["websites"][0]["id"] == "site-1"


@patch("mantecato_cli.main.AppState.connect")
def test_timeseries_keeps_segment_as_separate_filter_group(mock_connect: MagicMock) -> None:
    api = MagicMock()
    api.post.return_value = {
        "schema_version": "1",
        "query": {},
        "comparison": None,
        "totals": {},
        "rows": [],
    }
    user = UserConfig(profiles={}, segments={"tier1": ["country:in:US,GB"]})
    mock_connect.return_value = (api, user)
    result = runner.invoke(
        app,
        [
            "timeseries",
            "-w",
            "site-1",
            "--filter",
            "country:eq:US",
            "--segment",
            "tier1",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = api.post.call_args.args[1]
    assert payload["filters"] == ["country:eq:US"]
    assert payload["filter_groups"] == [["country:in:US,GB"]]
