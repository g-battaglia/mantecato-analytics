"""Tests for the /health/ endpoint.

Covers:
- GET /health/ returns 200 JSON when the default DB is reachable
- Response payload contains status=ok and database=ok on success
- GET /health/ returns 503 JSON when the default DB is unreachable
- Response payload contains status=unhealthy and database=error on failure
- No secrets leaked in error response
- No login required
- API key middleware does not interfere (no Authorization header needed)
- Static safety: no write SQL in health check code
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.db import OperationalError
from django.test import Client  # noqa: TC002


class TestHealthCheckSuccess:
    """Healthy default DB → 200 with ok payload."""

    @patch("apps.core.views.connections")
    def test_returns_200(self, mock_connections: MagicMock, client: Client) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        assert response.status_code == 200

    @patch("apps.core.views.connections")
    def test_content_type_json(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        assert response["Content-Type"] == "application/json"

    @patch("apps.core.views.connections")
    def test_payload_status_ok(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        data = json.loads(response.content)
        assert data["status"] == "ok"

    @patch("apps.core.views.connections")
    def test_payload_database_ok(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        data = json.loads(response.content)
        assert data["database"] == "ok"


class TestHealthCheckFailure:
    """Unreachable default DB → 503 with error payload."""

    @patch("apps.core.views.connections")
    def test_returns_503_on_db_error(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        mock_connections.__getitem__.side_effect = OperationalError("connection refused")

        response = client.get("/health/")
        assert response.status_code == 503

    @patch("apps.core.views.connections")
    def test_payload_status_unhealthy(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        mock_connections.__getitem__.side_effect = OperationalError("connection refused")

        response = client.get("/health/")
        data = json.loads(response.content)
        assert data["status"] == "unhealthy"

    @patch("apps.core.views.connections")
    def test_payload_database_error(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        mock_connections.__getitem__.side_effect = OperationalError("connection refused")

        response = client.get("/health/")
        data = json.loads(response.content)
        assert data["database"] == "error"

    @patch("apps.core.views.connections")
    def test_cursor_execute_error_returns_503(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        cursor = MagicMock()
        cursor.execute.side_effect = OperationalError("query failed")
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        assert response.status_code == 503
        data = json.loads(response.content)
        assert data["status"] == "unhealthy"

    @patch("apps.core.views.connections")
    def test_no_secrets_leaked_in_error(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        mock_connections.__getitem__.side_effect = OperationalError(
            "connection to db.example.com:5432 with user=admin failed"
        )

        response = client.get("/health/")
        content = response.content.decode()
        assert "db.example.com" not in content
        assert "admin" not in content
        assert "5432" not in content


class TestHealthCheckNoAuth:
    """Health endpoint must work without any authentication."""

    def test_no_login_required(self, client: Client) -> None:
        """Even without a DB mock, the endpoint URL resolves and doesn't redirect."""
        response = client.get("/health/")
        # Won't be 302 redirect to login — either 200 or 503
        assert response.status_code in (200, 503)

    @patch("apps.core.views.connections")
    def test_no_api_key_required(
        self, mock_connections: MagicMock, client: Client
    ) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        mock_connections.__getitem__.return_value.cursor.return_value = cursor

        response = client.get("/health/")
        assert response.status_code == 200


class TestHealthCheckStaticSafety:
    """Health check view must not contain write SQL."""

    WRITE_PATTERN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
        re.IGNORECASE,
    )

    def test_views_module_has_no_write_sql(self) -> None:
        import apps.core.views as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert self.WRITE_PATTERN.search(source) is None
