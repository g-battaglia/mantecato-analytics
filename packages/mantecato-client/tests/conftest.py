from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mantecato_client import MantecatoClient

BASE_URL = "https://analytics.test"
API_KEY = "mtk_test_key_123"


class MockTransport(httpx.BaseTransport):
    """Records requests and returns canned JSON responses."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.response_json: Any = {}
        self.response_status: int = 200

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = request.content.decode()

        self.requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "params": dict(request.url.params),
                "headers": dict(request.headers),
                "body": body,
            }
        )

        return httpx.Response(
            status_code=self.response_status,
            json=self.response_json,
        )

    @property
    def last(self) -> dict[str, Any]:
        return self.requests[-1]


@pytest.fixture
def transport() -> MockTransport:
    return MockTransport()


@pytest.fixture
def client(transport: MockTransport) -> MantecatoClient:
    http_client = httpx.Client(transport=transport)
    return MantecatoClient(BASE_URL, api_key=API_KEY, httpx_client=http_client)
