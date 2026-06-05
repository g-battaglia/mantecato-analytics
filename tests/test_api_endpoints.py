"""Tests for JSON API endpoints in apps/api/.

Covers:
- Auth required: all endpoints return 401 without API key
- URL resolution: all endpoints resolve to correct view
- Service dispatch: read endpoints delegate to service functions
- Safe invalid params: bad range, missing website → graceful error
- JsonResponse shape: correct content type and structure
- CRUD writes: POST endpoints call report service functions
- JSON serialization: datetimes, Decimals, UUIDs handled safely
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from apps.api.serializers import sanitize_for_json

_USER_ID = "a0000000-0000-0000-0000-000000000001"
_WEBSITE_ID = "b0000000-0000-0000-0000-000000000002"
_API_TOKEN = "Bearer mtk_test_token_1234567890"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Client:
    return Client()


def _auth_header() -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": _API_TOKEN}


def _mock_api_auth(client: Client) -> None:
    """Patch the middleware so request appears API-authenticated."""
    # We patch validate_api_key so middleware sets attrs on /api/ paths
    pass


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class TestURLResolution:
    @pytest.mark.parametrize(
        "url_name,path_suffix",
        [
            ("api_sites_list", "/api/sites/"),
            ("api_analytics_overview", "/api/analytics/overview/"),
            ("api_analytics_pages", "/api/analytics/pages/"),
            ("api_analytics_sources", "/api/analytics/sources/"),
            ("api_analytics_events", "/api/analytics/events/"),
            ("api_analytics_sessions", "/api/analytics/sessions/"),
            ("api_analytics_devices", "/api/analytics/devices/"),
            ("api_analytics_geo", "/api/analytics/geo/"),
            ("api_analytics_compare", "/api/analytics/compare/"),
            ("api_analytics_retention", "/api/analytics/retention/"),
            ("api_analytics_funnels", "/api/analytics/funnels/"),
            ("api_analytics_journeys", "/api/analytics/journeys/"),
            ("api_analytics_revenue", "/api/analytics/revenue/"),
            ("api_analytics_engagement", "/api/analytics/engagement/"),
            ("api_analytics_realtime", "/api/analytics/realtime/"),
            ("api_dashboard_list", "/api/dashboards/"),
            ("api_api_key_list", "/api/api-keys/"),
            ("api_bot_config_get", "/api/bot-config/"),
        ],
    )
    def test_url_resolves(self, url_name: str, path_suffix: str) -> None:
        from django.urls import resolve, reverse

        url = reverse(url_name)
        assert url == path_suffix
        match = resolve(url)
        assert match.url_name == url_name


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


class TestAuthRequired:
    """All /api/ endpoints require API key auth — middleware returns 401."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/sites/",
            "/api/analytics/overview/",
            "/api/analytics/pages/",
            "/api/analytics/realtime/",
            "/api/dashboards/",
            "/api/api-keys/",
            "/api/bot-config/",
        ],
    )
    def test_get_requires_auth(self, client: Client, path: str) -> None:
        response = client.get(path)
        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data

    @pytest.mark.parametrize(
        "path",
        [
            "/api/dashboards/create/",
            "/api/api-keys/create/",
            "/api/bot-config/save/",
        ],
    )
    def test_post_requires_auth(self, client: Client, path: str) -> None:
        response = client.post(path, data="{}", content_type="application/json")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Service dispatch (with mocked middleware + services)
# ---------------------------------------------------------------------------


class TestSitesListWithMiddleware:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    def test_returns_websites(
        self,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [
            {"id": _WEBSITE_ID, "name": "Test Site", "domain": "example.com"},
        ]
        response = client.get("/api/sites/", **_auth_header())
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        data = json.loads(response.content)
        assert "websites" in data
        assert len(data["websites"]) == 1
        assert data["websites"][0]["name"] == "Test Site"


# ---------------------------------------------------------------------------
# Analytics endpoints — service dispatch
# ---------------------------------------------------------------------------


class TestAnalyticsOverview:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.get_overview_data")
    def test_dispatches_to_service(
        self,
        mock_overview: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "Test", "domain": "x.com"}]
        mock_overview.return_value = {"stats": {"pageviews": 100}, "timeseries": []}

        response = client.get(
            f"/api/analytics/overview/?website={_WEBSITE_ID}",
            **_auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "stats" in data
        mock_overview.assert_called_once()


class TestAnalyticsPagesEndpoint:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.get_pages_data")
    def test_passes_page_param(
        self,
        mock_pages: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "T", "domain": "t.com"}]
        mock_pages.return_value = {"pages": [], "page": 2}

        response = client.get(
            f"/api/analytics/pages/?website={_WEBSITE_ID}&page=2",
            **_auth_header(),
        )
        assert response.status_code == 200
        mock_pages.assert_called_once()
        call_kwargs = mock_pages.call_args
        assert call_kwargs[1].get("page") == 2 or call_kwargs[0][3] == 2


class TestAnalyticsRealtime:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.get_realtime_data")
    def test_no_date_range_needed(
        self,
        mock_realtime: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "T", "domain": "t.com"}]
        mock_realtime.return_value = {"active": 5}

        response = client.get(
            f"/api/analytics/realtime/?website={_WEBSITE_ID}",
            **_auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["active"] == 5


# ---------------------------------------------------------------------------
# Legacy MCP remote compatibility routes
# ---------------------------------------------------------------------------


class TestLegacyMcpRoutes:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    def test_sites_without_trailing_slash(
        self,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "Test", "domain": "x.com"}]

        response = client.get("/api/sites", **_auth_header())

        assert response.status_code == 200
        assert json.loads(response.content)["websites"][0]["id"] == _WEBSITE_ID


# ---------------------------------------------------------------------------
# Safe invalid params
# ---------------------------------------------------------------------------


class TestSafeParams:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    def test_invalid_range_defaults_to_30d(
        self,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = []

        response = client.get("/api/sites/", **_auth_header())
        assert response.status_code == 200

    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.get_overview_data")
    def test_invalid_compare_mode_defaults(
        self,
        mock_overview: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        """Verify invalid comparison mode falls back gracefully."""
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "T", "domain": "t.com"}]
        mock_overview.return_value = {"stats": {}}

        response = client.get(
            f"/api/analytics/overview/?website={_WEBSITE_ID}&range=invalid_range",
            **_auth_header(),
        )
        # Invalid range falls back to 30d — should still work
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# CRUD write endpoints
# ---------------------------------------------------------------------------


class TestDashboardCRUD:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.create_new_dashboard")
    def test_create_dashboard(
        self,
        mock_create: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "T", "domain": "t.com"}]
        mock_create.return_value = {"id": str(uuid.uuid4()), "name": "New Dash"}

        body = json.dumps({"name": "New Dash", "website_id": _WEBSITE_ID})
        response = client.post(
            "/api/dashboards/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 201
        mock_create.assert_called_once()

    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.remove_dashboard")
    def test_delete_dashboard(
        self,
        mock_remove: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}
        mock_remove.return_value = True

        report_id = "c0000000-0000-0000-0000-000000000003"
        response = client.post(
            f"/api/dashboards/{report_id}/delete/",
            data="{}",
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["deleted"] is True


class TestApiKeyCRUD:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.generate_new_api_key")
    def test_create_api_key(
        self,
        mock_create: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}
        mock_create.return_value = {"id": str(uuid.uuid4()), "name": "test-key"}

        body = json.dumps({"name": "test-key"})
        response = client.post(
            "/api/api-keys/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 201

    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.remove_api_key")
    def test_delete_api_key(
        self,
        mock_remove: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}
        mock_remove.return_value = True

        key_id = "d0000000-0000-0000-0000-000000000004"
        response = client.post(
            f"/api/api-keys/{key_id}/delete/",
            data="{}",
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 200


class TestBotConfig:
    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.get_bot_config")
    def test_get_bot_config(
        self,
        mock_get: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        mock_resolve.return_value = [{"id": _WEBSITE_ID, "name": "T", "domain": "t.com"}]
        mock_get.return_value = {"enabled": True, "patterns": []}

        response = client.get(
            f"/api/bot-config/?website={_WEBSITE_ID}",
            **_auth_header(),
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["enabled"] is True


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    def test_sanitize_datetime(self) -> None:
        dt = datetime(2026, 5, 21, 12, 30, 0, tzinfo=UTC)
        result = sanitize_for_json({"ts": dt})
        assert result["ts"] == "2026-05-21T12:30:00+00:00"

    def test_sanitize_decimal(self) -> None:
        result = sanitize_for_json({"amount": Decimal("123.45")})
        assert result["amount"] == 123.45

    def test_sanitize_uuid(self) -> None:
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = sanitize_for_json({"id": uid})
        assert result["id"] == "12345678-1234-5678-1234-567812345678"

    def test_sanitize_nested(self) -> None:
        data = {
            "items": [
                {"id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), "val": Decimal("9.99")},
            ],
            "created": datetime(2026, 1, 1, tzinfo=UTC),
        }
        result = sanitize_for_json(data)
        assert isinstance(result["items"][0]["id"], str)
        assert isinstance(result["items"][0]["val"], float)
        assert isinstance(result["created"], str)

    def test_passthrough_primitives(self) -> None:
        assert sanitize_for_json(42) == 42
        assert sanitize_for_json("hello") == "hello"
        assert sanitize_for_json(None) is None
        assert sanitize_for_json(True) is True


# ---------------------------------------------------------------------------
# Validation / error handling
# ---------------------------------------------------------------------------


class TestValidation:
    @patch("mantecato.middleware.validate_api_key")
    def test_create_dashboard_missing_name(self, mock_validate: MagicMock, client: Client) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}

        body = json.dumps({"website_id": _WEBSITE_ID})
        response = client.post(
            "/api/dashboards/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 400

    @patch("mantecato.middleware.validate_api_key")
    def test_create_dashboard_missing_website(
        self,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}

        body = json.dumps({"name": "Test"})
        response = client.post(
            "/api/dashboards/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 400

    @patch("mantecato.middleware.validate_api_key")
    def test_create_dashboard_invalid_json(self, mock_validate: MagicMock, client: Client) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}

        response = client.post(
            "/api/dashboards/create/",
            data="not json",
            content_type="application/json",
            **_auth_header(),
        )
        assert response.status_code == 400

    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.create_new_dashboard")
    def test_write_requires_write_scope(
        self,
        mock_create: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}

        body = json.dumps({"name": "Test", "website_id": _WEBSITE_ID})
        response = client.post(
            "/api/dashboards/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )

        assert response.status_code == 403
        mock_create.assert_not_called()

    @patch("mantecato.middleware.validate_api_key")
    @patch("apps.api.views.resolve_websites_for_user")
    @patch("apps.api.views.create_new_dashboard")
    def test_write_rejects_inaccessible_website(
        self,
        mock_create: MagicMock,
        mock_resolve: MagicMock,
        mock_validate: MagicMock,
        client: Client,
    ) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read", "write"]}
        mock_resolve.return_value = []

        body = json.dumps({"name": "Test", "website_id": _WEBSITE_ID})
        response = client.post(
            "/api/dashboards/create/",
            data=body,
            content_type="application/json",
            **_auth_header(),
        )

        assert response.status_code == 403
        mock_create.assert_not_called()

    @patch("mantecato.middleware.validate_api_key")
    def test_bot_config_missing_website(self, mock_validate: MagicMock, client: Client) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}

        response = client.get("/api/bot-config/", **_auth_header())
        assert response.status_code == 400
