from __future__ import annotations

from mantecato_client import MantecatoClient
from tests.conftest import MockTransport


class TestOverview:
    def test_basic_call(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"stats": {}, "timeseries": []}
        client.analytics.overview("site-1", date_range="30d")
        assert transport.last["path"] == "/api/analytics/overview/"
        assert transport.last["params"]["website"] == "site-1"
        assert transport.last["params"]["range"] == "30d"

    def test_custom_date_range(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.overview("site-1", start="2026-01-01", end="2026-01-31")
        assert transport.last["params"]["start"] == "2026-01-01"
        assert transport.last["params"]["end"] == "2026-01-31"

    def test_with_filters(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.overview(
            "site-1",
            date_range="7d",
            filters=["country:eq:IT", "browser:eq:Chrome"],
        )
        params = transport.last["params"]
        assert "filter" in params

    def test_bot_filter(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.overview("site-1", bot_filter=True)
        assert transport.last["params"]["bot_filter"] == "1"


class TestPages:
    def test_with_page(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"pages": []}
        client.analytics.pages("site-1", date_range="7d", page=2)
        assert transport.last["params"]["page"] == "2"

    def test_without_page(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"pages": []}
        client.analytics.pages("site-1")
        assert "page" not in transport.last["params"]


class TestGeo:
    def test_country_level(self, client: MantecatoClient, transport: MockTransport):
        # Privacy-first geo is country-level only — no region/city drilldown.
        transport.response_json = {"geo": [], "level": "country"}
        client.analytics.geo("site-1", date_range="30d")
        assert transport.last["path"] == "/api/analytics/geo/"
        assert transport.last["params"]["website"] == "site-1"


class TestCompare:
    def test_with_mode(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.compare("site-1", mode="previous_year")
        assert transport.last["params"]["mode"] == "previous_year"


class TestRealtime:
    def test_only_website(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"realtime": {"count": 42}}
        result = client.analytics.realtime("site-1")
        assert result["realtime"]["count"] == 42
        assert transport.last["params"]["website"] == "site-1"
        assert "range" not in transport.last["params"]


class TestAllEndpoints:
    """The privacy-first SDK surface: overview, pages, events, devices, geo, compare, realtime."""

    def test_events(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.events("s")
        assert transport.last["path"] == "/api/analytics/events/"

    def test_devices(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.devices("s")
        assert transport.last["path"] == "/api/analytics/devices/"

    def test_geo(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.geo("s")
        assert transport.last["path"] == "/api/analytics/geo/"

    def test_compare(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.compare("s")
        assert transport.last["path"] == "/api/analytics/compare/"

    def test_realtime(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.realtime("s")
        assert transport.last["path"] == "/api/analytics/realtime/"
