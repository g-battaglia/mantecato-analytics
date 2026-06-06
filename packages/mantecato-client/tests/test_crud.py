from __future__ import annotations

from mantecato_client import MantecatoClient
from tests.conftest import MockTransport

# ============================================================================
# Sites
# ============================================================================


class TestSites:
    def test_list(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"websites": [{"id": "w1", "name": "My Site"}]}
        result = client.sites.list()
        assert transport.last["method"] == "GET"
        assert transport.last["path"] == "/api/sites/"
        assert result["websites"][0]["id"] == "w1"


# ============================================================================
# Dashboards
# ============================================================================


class TestDashboards:
    def test_list(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"dashboards": []}
        client.dashboards.list()
        assert transport.last["method"] == "GET"
        assert transport.last["path"] == "/api/dashboards/"

    def test_list_with_website(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"dashboards": []}
        client.dashboards.list(website_id="w1")
        assert transport.last["params"]["website"] == "w1"

    def test_get(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"id": "d1", "name": "Dash"}
        result = client.dashboards.get("d1")
        assert transport.last["path"] == "/api/dashboards/d1/"
        assert result["name"] == "Dash"

    def test_create(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"id": "new-d"}
        transport.response_status = 201
        client.dashboards.create(name="New Dash", website_id="w1", config={"widgets": []})
        assert transport.last["method"] == "POST"
        assert transport.last["body"]["name"] == "New Dash"
        assert transport.last["body"]["website_id"] == "w1"
        assert transport.last["body"]["config"] == {"widgets": []}

    def test_update(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"id": "d1"}
        client.dashboards.update("d1", name="Renamed")
        assert transport.last["method"] == "POST"
        assert transport.last["path"] == "/api/dashboards/d1/update/"
        assert transport.last["body"]["name"] == "Renamed"

    def test_delete(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"deleted": True}
        result = client.dashboards.delete("d1")
        assert transport.last["method"] == "POST"
        assert transport.last["path"] == "/api/dashboards/d1/delete/"
        assert result["deleted"] is True


# ============================================================================
# API Keys
# ============================================================================


class TestApiKeys:
    def test_list(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"api_keys": []}
        client.api_keys.list()
        assert transport.last["method"] == "GET"
        assert transport.last["path"] == "/api/api-keys/"

    def test_create(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"id": "k1", "key": "mtk_xxx"}
        transport.response_status = 201
        client.api_keys.create(name="CI Key", scopes=["read"])
        assert transport.last["body"]["name"] == "CI Key"
        assert transport.last["body"]["scopes"] == ["read"]

    def test_create_without_scopes(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"id": "k1"}
        transport.response_status = 201
        client.api_keys.create(name="Default Key")
        assert "scopes" not in transport.last["body"]

    def test_delete(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"deleted": True}
        client.api_keys.delete("k1")
        assert transport.last["path"] == "/api/api-keys/k1/delete/"


# ============================================================================
# Bot Config
# ============================================================================


class TestBotConfig:
    def test_get(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"enabled": True, "patterns": []}
        result = client.bot_config.get(website_id="w1")
        assert transport.last["params"]["website"] == "w1"
        assert result["enabled"] is True

    def test_save(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"enabled": False}
        client.bot_config.save(website_id="w1", config={"enabled": False})
        assert transport.last["body"]["website_id"] == "w1"
        assert transport.last["body"]["config"]["enabled"] is False
