from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mantecato_mcp.config import ConfigError, load_config
from mantecato_mcp.server import compare_breakdown, list_sites, query_timeseries


def test_config_requires_https_except_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANTECATO_URL", "http://analytics.example")
    monkeypatch.setenv("MANTECATO_API_KEY", "mtk_secret")
    with pytest.raises(ConfigError):
        load_config()


@pytest.mark.asyncio
@patch("mantecato_mcp.server.get", new_callable=AsyncMock)
async def test_list_sites_uses_existing_api(mock_get: AsyncMock) -> None:
    mock_get.return_value = {"websites": []}
    assert await list_sites() == {"websites": []}
    mock_get.assert_awaited_once_with("/api/sites/")


@pytest.mark.asyncio
@patch("mantecato_mcp.server.post", new_callable=AsyncMock)
async def test_timeseries_has_no_credential_tool_arguments(mock_post: AsyncMock) -> None:
    mock_post.return_value = {"schema_version": "1", "rows": []}
    result = await query_timeseries(
        "site-1",
        dimensions=["country"],
        filters=["country:in:US,GB"],
    )
    assert result["schema_version"] == "1"
    body = mock_post.await_args.args[1]
    assert body["website_id"] == "site-1"
    assert "api_key" not in body and "url" not in body


@pytest.mark.asyncio
@patch("mantecato_mcp.server.post", new_callable=AsyncMock)
async def test_compare_calls_v1_endpoint(mock_post: AsyncMock) -> None:
    mock_post.return_value = {"schema_version": "1", "rows": []}
    await compare_breakdown("site-1", "country", direction="losses")
    mock_post.assert_awaited_once()
    assert mock_post.await_args.args[0] == "/api/v1/analytics/compare/"
    assert mock_post.await_args.args[1]["direction"] == "losses"


@pytest.mark.asyncio
async def test_real_stdio_client_discovers_read_only_tools() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mantecato_mcp.server"],
        env={
            **os.environ,
            "MANTECATO_URL": "http://localhost:8000",
            "MANTECATO_API_KEY": "mtk_test",
        },
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.list_tools()
    names = {tool.name for tool in result.tools}
    assert {
        "list_sites",
        "describe_analytics",
        "query_metrics",
        "query_timeseries",
        "compare_breakdown",
        "traffic_quality",
        "list_dimension_values",
    } <= names
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in result.tools)
