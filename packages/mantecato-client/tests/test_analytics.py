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
    def test_with_country(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.geo("site-1", country="IT")
        assert transport.last["params"]["country"] == "IT"

    def test_with_region(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.geo("site-1", country="US", region="CA")
        assert transport.last["params"]["country"] == "US"
        assert transport.last["params"]["region"] == "CA"


class TestCompare:
    def test_with_mode(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.compare("site-1", mode="previous_year")
        assert transport.last["params"]["mode"] == "previous_year"


class TestRetention:
    def test_with_granularity(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.retention("site-1", granularity="month")
        assert transport.last["params"]["granularity"] == "month"

    def test_no_filters_param(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.retention("site-1")
        assert "filter" not in transport.last["params"]


class TestFunnels:
    def test_step_encoding(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.funnels(
            "site-1",
            steps=[("url", "/"), ("event", "signup")],
            window=60,
        )
        params = transport.last["params"]
        assert params["step_type.0"] == "url"
        assert params["step_value.0"] == "/"
        assert params["step_type.1"] == "event"
        assert params["step_value.1"] == "signup"
        assert params["window"] == "60"

    def test_no_steps(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.funnels("site-1")
        assert "step_type.0" not in transport.last["params"]


class TestJourneys:
    def test_with_params(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.journeys("site-1", path_length=4, limit=50)
        assert transport.last["params"]["path_length"] == "4"
        assert transport.last["params"]["limit"] == "50"


class TestRealtime:
    def test_only_website(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {"active": 42}
        result = client.analytics.realtime("site-1")
        assert result["active"] == 42
        assert transport.last["params"]["website"] == "site-1"
        assert "range" not in transport.last["params"]


class TestAllEndpoints:
    def test_sources(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.sources("s")
        assert transport.last["path"] == "/api/analytics/sources/"

    def test_events(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.events("s")
        assert transport.last["path"] == "/api/analytics/events/"

    def test_sessions(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.sessions("s", page=3)
        assert transport.last["path"] == "/api/analytics/sessions/"
        assert transport.last["params"]["page"] == "3"

    def test_devices(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.devices("s")
        assert transport.last["path"] == "/api/analytics/devices/"

    def test_revenue(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.revenue("s")
        assert transport.last["path"] == "/api/analytics/revenue/"

    def test_engagement(self, client: MantecatoClient, transport: MockTransport):
        transport.response_json = {}
        client.analytics.engagement("s")
        assert transport.last["path"] == "/api/analytics/engagement/"
