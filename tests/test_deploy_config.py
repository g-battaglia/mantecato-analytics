"""Tests for Docker/deployment configuration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_exists_and_uses_gunicorn() -> None:
    dockerfile = (ROOT / "Dockerfile.standalone").read_text()
    assert "gunicorn mantecato.wsgi:application" in dockerfile
    assert "collectstatic --noinput" in dockerfile


def test_docker_configs_run_migrations() -> None:
    dockerfile = (ROOT / "Dockerfile.standalone").read_text()
    assert "manage.py migrate" in dockerfile
    assert "makemigrations" not in dockerfile


def test_static_and_security_settings_are_defined() -> None:
    assert settings.STATIC_ROOT.name == "staticfiles"
    assert hasattr(settings, "CSRF_TRUSTED_ORIGINS")
    assert hasattr(settings, "SECURE_SSL_REDIRECT")
    assert hasattr(settings, "SESSION_COOKIE_SECURE")
    assert hasattr(settings, "CSRF_COOKIE_SECURE")


def test_env_example_documents_production_vars() -> None:
    env_example = (ROOT / ".env.example").read_text()
    assert "ALLOWED_HOSTS=" in env_example
    assert "CSRF_TRUSTED_ORIGINS=" in env_example
    assert "USE_SECURE_PROXY_SSL_HEADER=" in env_example
    assert "UMAMI_DATABASE_URL=" in env_example
    assert "UMAMI_IMPORT_ON_DEPLOY=" in env_example


def test_render_blueprint_is_portable_and_private() -> None:
    blueprint = (ROOT / "render.yaml").read_text()
    assert "repo:" not in blueprint
    assert "ipAllowList: []" in blueprint
    assert "python manage.py migrate" in blueprint
    assert "python manage.py importumamienv" in blueprint
    assert "preDeployCommand:" not in blueprint
    assert "UMAMI_DATABASE_URL" in blueprint
    assert 'value: "Europe/Rome"' in blueprint


def test_production_database_url_ignores_test_database_url() -> None:
    from mantecato.config import get_database_url

    with patch.dict(
        "os.environ",
        {
            "DATABASE_URL": "postgres://prod:prod@prod-db:5432/umami",
            "TEST_DATABASE_URL": "postgres://test:test@test-db:5432/umami",
        },
    ):
        assert get_database_url(debug=False) == "postgres://prod:prod@prod-db:5432/umami"
        assert get_database_url(debug=True) == "postgres://test:test@test-db:5432/umami"


def test_require_database_url_enforced_in_production() -> None:
    from django.core.exceptions import ImproperlyConfigured

    from mantecato.config import require_database_url

    # Production without a database must fail loudly rather than fall back to SQLite.
    with pytest.raises(ImproperlyConfigured):
        require_database_url("", debug=False)
    # Development is allowed to use the SQLite fallback.
    require_database_url("", debug=True)
    # Production with a database URL is fine.
    require_database_url("postgres://u:p@h:5432/db", debug=False)


def test_open_hosts_warning() -> None:
    import os

    from mantecato.config import open_hosts_warning

    # Restricted hosts: no warning.
    assert open_hosts_warning(["example.com"]) is None
    # Open, off Railway: generic message.
    with patch.dict(os.environ, {}, clear=True):
        msg = open_hosts_warning(["*"])
        assert msg is not None and "Set the ALLOWED_HOSTS" in msg
    # Open, on Railway: message suggests the exact value to set.
    with patch.dict(os.environ, {"RAILWAY_PUBLIC_DOMAIN": "myapp.up.railway.app"}, clear=True):
        msg = open_hosts_warning(["*"])
        assert "myapp.up.railway.app,healthcheck.railway.app" in msg


def test_health_endpoint_exempt_from_ssl_redirect() -> None:
    # Platform health checks hit /health/ over plain HTTP; it must not 301-redirect,
    # otherwise the check fails even though the app is healthy.
    assert any("health" in pattern for pattern in settings.SECURE_REDIRECT_EXEMPT)
