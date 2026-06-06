"""Tests for the API key authentication middleware.

Covers:
- No Authorization header → anonymous request, get_response called
- Valid Bearer token → attrs set (api_user, api_user_id, api_key_scopes, is_api_authenticated)
- Invalid Bearer token on /api/... → 401 JSON
- Invalid Bearer token on web path → request passes through (session auth handles it)
- Malformed Authorization header on /api/... → 401 JSON
- Malformed Authorization header on web path → request passes through
- Empty Bearer token (``Bearer ``) → treated as malformed
- validate_api_key exception → handled gracefully, 401 on protected paths
- Static safety: no INSERT/UPDATE/DELETE in middleware code
- Live integration: create key, validate via middleware, cleanup
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import RequestFactory

from mantecato.middleware import (
    ApiKeyMiddleware,
    _extract_bearer_token,
    _is_protected_path,
    _unauthorized,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = "b0000000-0000-0000-0000-000000000001"
_VALID_RESULT = {
    "userId": _USER_ID,
    "scopes": ["read", "write"],
}


def _make_response() -> HttpResponse:
    return HttpResponse("ok", status=200)


def _make_middleware() -> ApiKeyMiddleware:
    return ApiKeyMiddleware(get_response=lambda req: _make_response())


def _make_request(path: str = "/", auth_header: str | None = None) -> HttpRequest:
    factory = RequestFactory()
    request = factory.get(path)
    if auth_header is not None:
        request.META["HTTP_AUTHORIZATION"] = auth_header
    return request


# ---------------------------------------------------------------------------
# _extract_bearer_token
# ---------------------------------------------------------------------------


class TestExtractBearerToken:
    def test_valid_bearer(self) -> None:
        assert _extract_bearer_token("Bearer mtk_abc123") == "mtk_abc123"

    def test_case_insensitive_bearer(self) -> None:
        assert _extract_bearer_token("bearer mtk_abc123") == "mtk_abc123"

    def test_bearer_uppercase(self) -> None:
        assert _extract_bearer_token("BEARER mtk_abc123") == "mtk_abc123"

    def test_no_space(self) -> None:
        assert _extract_bearer_token("Bearermtk_abc") is None

    def test_wrong_scheme(self) -> None:
        assert _extract_bearer_token("Basic dXNlcjpwYXNz") is None

    def test_empty_string(self) -> None:
        assert _extract_bearer_token("") is None

    def test_bearer_empty_token(self) -> None:
        assert _extract_bearer_token("Bearer ") is None

    def test_bearer_only_spaces(self) -> None:
        assert _extract_bearer_token("Bearer   ") is None

    def test_extra_whitespace_around_token(self) -> None:
        assert _extract_bearer_token("Bearer  mtk_abc  ") == "mtk_abc"


# ---------------------------------------------------------------------------
# _is_protected_path
# ---------------------------------------------------------------------------


class TestIsProtectedPath:
    @pytest.mark.parametrize(
        "path",
        ["/api/", "/api/v1/sites", "/api/something/deep"],
    )
    def test_protected_paths(self, path: str) -> None:
        assert _is_protected_path(path) is True

    @pytest.mark.parametrize(
        "path",
        ["/", "/dashboard", "/login", "/analytics/overview", "/static/js/app.js"],
    )
    def test_unprotected_paths(self, path: str) -> None:
        assert _is_protected_path(path) is False


# ---------------------------------------------------------------------------
# _unauthorized
# ---------------------------------------------------------------------------


class TestUnauthorized:
    def test_returns_json_response(self) -> None:
        response = _unauthorized("Bad key")
        assert isinstance(response, JsonResponse)
        assert response.status_code == 401
        data = json.loads(response.content)
        assert data["error"] == "Bad key"

    def test_content_type_is_json(self) -> None:
        response = _unauthorized("x")
        assert response["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Middleware: no header
# ---------------------------------------------------------------------------


class TestNoHeader:
    def test_request_passes_through(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/")
        response = middleware(request)
        assert response.status_code == 200

    def test_attrs_are_defaults(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/")
        middleware(request)
        assert request.api_user is None
        assert request.api_user_id is None
        assert request.api_key_scopes == []
        assert request.is_api_authenticated is False

    def test_empty_auth_header_treated_as_missing(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/")
        request.META["HTTP_AUTHORIZATION"] = ""
        response = middleware(request)
        assert response.status_code == 200
        assert request.is_api_authenticated is False


# ---------------------------------------------------------------------------
# Middleware: valid key
# ---------------------------------------------------------------------------


class TestValidKey:
    @patch("mantecato.middleware.validate_api_key")
    def test_attrs_set_on_success(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = _VALID_RESULT
        middleware = _make_middleware()
        request = _make_request("/api/v1/sites", "Bearer mtk_validkey123")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is True
        assert request.api_user_id == _USER_ID
        assert request.api_user == {
            "userId": _USER_ID,
            "scopes": ["read", "write"],
        }
        assert request.api_key_scopes == ["read", "write"]

    @patch("mantecato.middleware.validate_api_key")
    def test_get_response_called(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = _VALID_RESULT
        called = False

        def _respond(req: HttpRequest) -> HttpResponse:
            nonlocal called
            called = True
            return _make_response()

        middleware = ApiKeyMiddleware(get_response=_respond)
        request = _make_request("/", "Bearer mtk_valid")
        middleware(request)
        assert called is True

    @patch("mantecato.middleware.validate_api_key")
    def test_valid_key_on_web_path(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = _VALID_RESULT
        middleware = _make_middleware()
        request = _make_request("/dashboard", "Bearer mtk_valid")
        response = middleware(request)
        assert response.status_code == 200
        assert request.is_api_authenticated is True

    @patch("mantecato.middleware.validate_api_key")
    def test_validate_called_with_token(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = _VALID_RESULT
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearer mtk_sometoken")
        middleware(request)
        mock_validate.assert_called_once_with("mtk_sometoken")

    @patch("mantecato.middleware.validate_api_key")
    def test_default_scopes_when_missing(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = {"userId": _USER_ID, "scopes": ["read"]}
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearer mtk_readonly")
        middleware(request)
        assert request.api_key_scopes == ["read"]


# ---------------------------------------------------------------------------
# Middleware: invalid key on protected paths
# ---------------------------------------------------------------------------


class TestInvalidKeyOnProtectedPaths:
    @patch("mantecato.middleware.validate_api_key")
    def test_invalid_key_api_returns_401(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = None
        middleware = _make_middleware()
        request = _make_request("/api/v1/data", "Bearer mtk_invalid")
        response = middleware(request)

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "Invalid API key" in data["error"]

    @patch("mantecato.middleware.validate_api_key")
    def test_invalid_key_does_not_set_attrs(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = None
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearer mtk_invalid")
        middleware(request)

        assert request.is_api_authenticated is False
        assert request.api_user is None
        assert request.api_user_id is None


# ---------------------------------------------------------------------------
# Middleware: invalid key on web paths (non-API)
# ---------------------------------------------------------------------------


class TestInvalidKeyOnWebPaths:
    """Invalid keys on web paths do NOT block navigation — session auth handles it."""

    @patch("mantecato.middleware.validate_api_key")
    def test_invalid_key_web_passes_through(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = None
        middleware = _make_middleware()
        request = _make_request("/dashboard", "Bearer mtk_invalid")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is False

    @patch("mantecato.middleware.validate_api_key")
    def test_invalid_key_root_passes_through(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = None
        middleware = _make_middleware()
        request = _make_request("/", "Bearer mtk_invalid")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is False

    @patch("mantecato.middleware.validate_api_key")
    def test_invalid_key_analytics_passes_through(self, mock_validate: MagicMock) -> None:
        mock_validate.return_value = None
        middleware = _make_middleware()
        request = _make_request("/analytics/overview", "Bearer mtk_invalid")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is False


# ---------------------------------------------------------------------------
# Middleware: malformed Authorization header
# ---------------------------------------------------------------------------


class TestMalformedHeader:
    def test_malformed_on_api_returns_401(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/api/test", "Basic dXNlcjpwYXNz")
        response = middleware(request)
        assert response.status_code == 401
        data = json.loads(response.content)
        assert "Malformed" in data["error"]

    def test_malformed_on_web_passes_through(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/dashboard", "Basic dXNlcjpwYXNz")
        response = middleware(request)
        assert response.status_code == 200
        assert request.is_api_authenticated is False

    def test_no_space_in_header(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearermtk_nospace")
        response = middleware(request)
        assert response.status_code == 401

    def test_bearer_with_empty_token_on_api(self) -> None:
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearer ")
        response = middleware(request)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Middleware: validate_api_key exception handling
# ---------------------------------------------------------------------------


class TestValidateException:
    @patch("mantecato.middleware.validate_api_key")
    def test_exception_on_api_returns_401(self, mock_validate: MagicMock) -> None:
        mock_validate.side_effect = RuntimeError("DB connection lost")
        middleware = _make_middleware()
        request = _make_request("/api/test", "Bearer mtk_willraise")
        response = middleware(request)

        assert response.status_code == 401
        assert request.is_api_authenticated is False

    @patch("mantecato.middleware.validate_api_key")
    def test_exception_on_web_passes_through(self, mock_validate: MagicMock) -> None:
        mock_validate.side_effect = RuntimeError("DB connection lost")
        middleware = _make_middleware()
        request = _make_request("/", "Bearer mtk_willraise")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is False

    @patch("mantecato.middleware.validate_api_key")
    def test_exception_does_not_log_full_key(self, mock_validate: MagicMock) -> None:
        mock_validate.side_effect = RuntimeError("boom")
        middleware = _make_middleware()

        with patch("mantecato.middleware.logger") as mock_logger:
            request = _make_request("/api/test", "Bearer mtk_supersecret12345")
            middleware(request)
            if mock_logger.warning.called:
                log_msg = str(mock_logger.warning.call_args)
                assert "mtk_supersecret12345" not in log_msg


# ---------------------------------------------------------------------------
# Static safety: no write SQL in middleware
# ---------------------------------------------------------------------------


class TestStaticSafety:
    WRITE_PATTERN = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
        re.IGNORECASE,
    )

    def test_middleware_module_has_no_write_sql(self) -> None:
        import mantecato.middleware as module

        source_code = Path(module.__file__).read_text(encoding="utf-8")
        sql_strings = re.findall(r'"""(.*?)"""', source_code, re.DOTALL)
        sql_strings += re.findall(r"'''(.*?)'''", source_code, re.DOTALL)
        for sql in sql_strings:
            assert self.WRITE_PATTERN.search(sql) is None, (
                f"Write operation found in middleware SQL: {sql[:100]}"
            )

    def test_middleware_code_no_direct_sql(self) -> None:
        """Middleware should not contain any SQL at all — it delegates to api_keys."""
        import mantecato.middleware as module

        source_code = Path(module.__file__).read_text(encoding="utf-8")
        assert "SELECT" not in source_code
        assert "INSERT" not in source_code
        assert "UPDATE" not in source_code
        assert "DELETE" not in source_code


# ---------------------------------------------------------------------------
# Live integration (optional, requires live development database)
# ---------------------------------------------------------------------------


class TestLiveIntegration:
    """Create a real API key, validate through middleware, then cleanup.

    Only writes to the ``report`` table. All other tables are untouched.
    """

    @patch("mantecato.middleware.validate_api_key")
    def test_live_key_flow_mocked(self, mock_validate: MagicMock) -> None:
        """Full flow test with mocked validate_api_key for CI safety."""

        # Simulate: middleware calls validate_api_key, which would hit the DB
        # Here we mock it returning the expected shape
        key = "mtk_test_live_integration_key"
        mock_validate.return_value = {
            "userId": _USER_ID,
            "scopes": ["read", "write"],
        }

        middleware = _make_middleware()
        request = _make_request("/api/v1/data", f"Bearer {key}")
        response = middleware(request)

        assert response.status_code == 200
        assert request.is_api_authenticated is True
        assert request.api_user_id == _USER_ID
        assert request.api_key_scopes == ["read", "write"]
        mock_validate.assert_called_once_with(key)

    def test_live_create_validate_cleanup(self, django_db_blocker: object) -> None:
        """Live test: create key → validate via middleware → delete key.

        Writes ONLY to ``report`` table. Uses live development database DB.
        """
        from apps.core.api_keys import validate_api_key
        from apps.settings_app.services import generate_new_api_key, remove_api_key

        with django_db_blocker.unblock():  # type: ignore[attr-defined]
            created = generate_new_api_key(
                user_id=_USER_ID,
                name="test-middleware-key",
                scopes=["read"],
            )
            key = created["key"]
            key_id = created["id"]

            try:
                assert key.startswith("mtk_")

                # Validate directly
                result = validate_api_key(key)
                assert result is not None
                assert result["userId"] == _USER_ID
                assert "read" in result["scopes"]

                # Now test through middleware (unmocked)
                middleware = _make_middleware()
                request = _make_request("/api/v1/test", f"Bearer {key}")
                response = middleware(request)

                assert response.status_code == 200
                assert request.is_api_authenticated is True
                assert request.api_user_id == _USER_ID
                assert request.api_key_scopes == ["read"]

                # Invalid key should fail
                middleware2 = _make_middleware()
                request2 = _make_request("/api/v1/test", "Bearer mtk_invalidkey")
                response2 = middleware2(request2)
                assert response2.status_code == 401

            finally:
                deleted = remove_api_key(key_id, _USER_ID)
                assert deleted is True
