from __future__ import annotations

import httpx
import pytest

from mantecato_client import (
    AuthError,
    MantecatoClient,
    MantecatoError,
    NotFoundError,
    ValidationError,
)
from tests.conftest import API_KEY, BASE_URL, MockTransport


class TestAuth:
    def test_bearer_header_on_every_request(
        self,
        client: MantecatoClient,
        transport: MockTransport,
    ):
        transport.response_json = {"websites": []}
        client.sites.list()
        assert transport.last["headers"]["authorization"] == f"Bearer {API_KEY}"

    def test_bearer_header_on_post(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"deleted": True}
        client.dashboards.delete("some-uuid")
        assert transport.last["headers"]["authorization"] == f"Bearer {API_KEY}"


class TestBaseUrl:
    def test_trailing_slash_stripped(self, transport: MockTransport):
        http = httpx.Client(transport=transport)
        c = MantecatoClient(f"{BASE_URL}/", api_key=API_KEY, httpx_client=http)
        transport.response_json = {"websites": []}
        c.sites.list()
        assert transport.last["url"].startswith(BASE_URL + "/api/")
        assert "//api/" not in transport.last["url"]


class TestErrorMapping:
    def test_400_raises_validation_error(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 400
        transport.response_json = {"error": "name is required."}
        with pytest.raises(ValidationError, match="name is required") as exc_info:
            client.dashboards.create(name="", website_id="x")
        assert exc_info.value.status_code == 400

    def test_401_raises_auth_error(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 401
        transport.response_json = {"error": "Invalid API key."}
        with pytest.raises(AuthError, match="Invalid API key"):
            client.sites.list()

    def test_403_raises_auth_error(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 403
        transport.response_json = {"error": "Website not accessible."}
        with pytest.raises(AuthError):
            client.analytics.overview("site-uuid")

    def test_404_raises_not_found(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 404
        transport.response_json = {"error": "Dashboard not found."}
        with pytest.raises(NotFoundError):
            client.dashboards.get("missing-uuid")

    def test_500_raises_base_error(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 500
        transport.response_json = {"error": "Internal server error"}
        with pytest.raises(MantecatoError) as exc_info:
            client.sites.list()
        assert exc_info.value.status_code == 500

    def test_error_preserves_response_body(self, client: MantecatoClient, transport: MockTransport):
        transport.response_status = 400
        transport.response_json = {"error": "bad", "detail": "extra"}
        with pytest.raises(ValidationError) as exc_info:
            client.sites.list()
        assert exc_info.value.response_body["detail"] == "extra"


class TestContextManager:
    def test_context_manager_closes(self):
        c = MantecatoClient(BASE_URL, api_key=API_KEY)
        with c:
            pass


class TestEndpointGroups:
    def test_all_groups_present(self, client: MantecatoClient):
        assert hasattr(client, "sites")
        assert hasattr(client, "analytics")
        assert hasattr(client, "dashboards")
        assert hasattr(client, "api_keys")
        assert hasattr(client, "bot_config")
