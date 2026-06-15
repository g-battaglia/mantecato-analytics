"""Tests for the UI-triggered Umami import (background, data-only, single-site).

Mirrors the hermetic style of ``tests/test_crud_pages.py``: sessions are
signed-cookie based, so ``force_login`` needs no database, and every service /
ORM boundary is mocked. Covers URL resolution, login + admin gating, the
form/POST flow, the HTMX progress partial, the ``DBProgress`` throttle, the
background job target, and the no-DSN-persistence guarantee.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.http import HttpResponse
    from django.test import Client

from apps.core.models import MantecatoUser

ADMIN_USER_ID = "b0000000-0000-0000-0000-000000000001"
TARGET_WEBSITE_ID = "a0000000-0000-0000-0000-000000000001"
SOURCE_WEBSITE_ID = "d0000000-0000-0000-0000-000000000099"
JOB_ID = "e0000000-0000-0000-0000-0000000000aa"
VALID_DSN = "postgresql://u:p@umami-db:5432/umami"

IMPORT_URL = "/settings/import/umami/"
STATUS_URL = f"/settings/import/umami/status/{JOB_ID}/"


def _make_user(role: str = "admin") -> MantecatoUser:
    """Build an in-memory user (no DB row); ``is_staff`` derives from *role*."""
    user = MantecatoUser(username=role, role=role)
    user.pk = ADMIN_USER_ID
    user.backend = "django.contrib.auth.backends.ModelBackend"
    return user


def _login(client: Client, user: MantecatoUser) -> None:
    """force_login without firing the last_login DB write."""
    from django.contrib.auth.signals import user_logged_in

    with patch.object(user_logged_in, "send", return_value=[]):
        client.force_login(user)


@contextmanager
def _patch_user(user: MantecatoUser) -> Generator[None, None, None]:
    """Patch ``AuthenticationMiddleware`` so ``request.user`` is *user*."""
    with patch(
        "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"
    ) as mock_process:
        mock_process.side_effect = lambda request: setattr(request, "user", user)
        yield


def _authed_get(client: Client, url: str, user: MantecatoUser | None = None) -> HttpResponse:
    user = user or _make_user("admin")
    _login(client, user)
    with _patch_user(user):
        return client.get(url)


def _authed_post(
    client: Client, url: str, data: dict | None = None, user: MantecatoUser | None = None
) -> HttpResponse:
    user = user or _make_user("admin")
    _login(client, user)
    with _patch_user(user):
        return client.post(url, data or {})


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class TestURLResolution:
    def test_import_url(self) -> None:
        from django.urls import reverse

        assert reverse("umami_import") == IMPORT_URL

    def test_status_url(self) -> None:
        from django.urls import reverse

        assert reverse("umami_import_status", kwargs={"job_id": JOB_ID}) == STATUS_URL


# ---------------------------------------------------------------------------
# Login requirement
# ---------------------------------------------------------------------------


class TestLoginRequired:
    @pytest.mark.parametrize("url", [IMPORT_URL, STATUS_URL])
    def test_get_redirects_to_login(self, client: Client, url: str) -> None:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_post_redirects_to_login(self, client: Client) -> None:
        response = client.post(IMPORT_URL, {})
        assert response.status_code == 302
        assert "/login/" in response.url


# ---------------------------------------------------------------------------
# Admin-only gating
# ---------------------------------------------------------------------------


class TestAdminOnly:
    def test_non_admin_get_forbidden(self, client: Client) -> None:
        response = _authed_get(client, IMPORT_URL, user=_make_user("user"))
        assert response.status_code == 403

    def test_non_admin_post_forbidden(self, client: Client) -> None:
        response = _authed_post(client, IMPORT_URL, {}, user=_make_user("user"))
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET form
# ---------------------------------------------------------------------------


class TestGetForm:
    @patch("apps.settings_app.views.get_latest_umami_import_job", return_value=None)
    @patch("apps.settings_app.views.resolve_websites_for_user", return_value=[])
    def test_renders_form(self, _sites: MagicMock, _job: MagicMock, client: Client) -> None:
        response = _authed_get(client, IMPORT_URL)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'name="source_dsn"' in html
        assert 'name="target_website"' in html
        assert 'name="source_website"' in html
        assert "csrfmiddlewaretoken" in html


# ---------------------------------------------------------------------------
# POST start import
# ---------------------------------------------------------------------------


class TestPostStart:
    @patch("apps.settings_app.views.start_umami_import_job", return_value={"id": JOB_ID})
    def test_valid_starts_and_redirects(self, mock_start: MagicMock, client: Client) -> None:
        response = _authed_post(
            client,
            IMPORT_URL,
            {
                "target_website": TARGET_WEBSITE_ID,
                "source_website": SOURCE_WEBSITE_ID,
                "source_dsn": VALID_DSN,
            },
        )
        assert response.status_code == 302
        assert f"?job={JOB_ID}" in response.url
        mock_start.assert_called_once()
        kwargs = mock_start.call_args.kwargs
        assert kwargs["source_dsn"] == VALID_DSN
        assert kwargs["target_website"] == TARGET_WEBSITE_ID
        assert kwargs["source_website"] == SOURCE_WEBSITE_ID
        assert kwargs["replace"] is False
        assert kwargs["since_date"] is None

    @patch("apps.settings_app.views.start_umami_import_job")
    def test_invalid_dsn_does_not_start(self, mock_start: MagicMock, client: Client) -> None:
        response = _authed_post(
            client,
            IMPORT_URL,
            {
                "target_website": TARGET_WEBSITE_ID,
                "source_website": SOURCE_WEBSITE_ID,
                "source_dsn": "not-a-dsn",
            },
        )
        assert response.status_code == 302
        mock_start.assert_not_called()

    @patch("apps.settings_app.views.start_umami_import_job")
    def test_invalid_uuid_does_not_start(self, mock_start: MagicMock, client: Client) -> None:
        response = _authed_post(
            client,
            IMPORT_URL,
            {
                "target_website": "not-a-uuid",
                "source_website": SOURCE_WEBSITE_ID,
                "source_dsn": VALID_DSN,
            },
        )
        assert response.status_code == 302
        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# HTMX progress partial
# ---------------------------------------------------------------------------


def _fake_job(*, status: str, is_active: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=JOB_ID,
        status=status,
        is_active=is_active,
        current_table="events" if is_active else None,
        imported_rows=5,
        total_rows=10,
        error_message=None,
    )


class TestStatusPartial:
    @patch("apps.settings_app.views.get_umami_import_job")
    def test_running_job_keeps_polling(self, mock_get: MagicMock, client: Client) -> None:
        mock_get.return_value = _fake_job(status="running", is_active=True)
        response = _authed_get(client, STATUS_URL)
        assert response.status_code == 200
        html = response.content.decode()
        assert 'hx-trigger="every 2s"' in html
        assert "running" in html

    @patch("apps.settings_app.views.get_umami_import_job")
    def test_finished_job_stops_polling(self, mock_get: MagicMock, client: Client) -> None:
        mock_get.return_value = _fake_job(status="success", is_active=False)
        response = _authed_get(client, STATUS_URL)
        assert response.status_code == 200
        html = response.content.decode()
        assert "hx-trigger" not in html


# ---------------------------------------------------------------------------
# DBProgress adapter (unit)
# ---------------------------------------------------------------------------


class TestDBProgress:
    @patch("apps.core.models.UmamiImportJob")
    def test_throttles_writes_and_tracks_table(self, mock_model: MagicMock) -> None:
        from apps.core.services import DBProgress

        update = mock_model.objects.filter.return_value.update
        progress = DBProgress(JOB_ID, flush_every=50_000)

        task = progress.add_task("Importing events", total=60_000)
        # add_task records current_table + the running total.
        assert update.call_count == 1
        assert update.call_args.kwargs["current_table"] == "events"
        assert update.call_args.kwargs["total_rows"] == 60_000

        for _ in range(4):
            progress.update(task, advance=10_000)
        assert update.call_count == 1  # 40k < 50k → no flush yet

        progress.update(task, advance=10_000)  # 50k → flush
        assert update.call_count == 2
        assert update.call_args.kwargs["imported_rows"] == 50_000

        progress.flush()  # explicit final flush
        assert update.call_count == 3


# ---------------------------------------------------------------------------
# Background job target (run synchronously in tests)
# ---------------------------------------------------------------------------


class TestRunImportJob:
    @patch("apps.core.services.connection")
    @patch("apps.core.models.UmamiImportJob")
    @patch("apps.core.services.UmamiImporter")
    def test_success_sequence(
        self, mock_importer_cls: MagicMock, mock_model: MagicMock, _conn: MagicMock
    ) -> None:
        from apps.core.services import run_umami_import_job

        importer = mock_importer_cls.return_value
        importer.connect.return_value = MagicMock()

        run_umami_import_job(
            JOB_ID,
            VALID_DSN,
            target_website=TARGET_WEBSITE_ID,
            source_website=SOURCE_WEBSITE_ID,
            since_date=None,
            replace=False,
        )

        importer.connect.assert_called_once()
        importer.run.assert_called_once()
        importer.replace_target_data.assert_not_called()
        statuses = [
            c.kwargs.get("status")
            for c in mock_model.objects.filter.return_value.update.call_args_list
        ]
        assert "running" in statuses
        assert "success" in statuses

    @patch("apps.core.services.connection")
    @patch("apps.core.models.UmamiImportJob")
    @patch("apps.core.services.UmamiImporter")
    def test_replace_calls_replace_target_data(
        self, mock_importer_cls: MagicMock, _model: MagicMock, _conn: MagicMock
    ) -> None:
        from apps.core.services import run_umami_import_job

        importer = mock_importer_cls.return_value
        importer.connect.return_value = MagicMock()

        run_umami_import_job(
            JOB_ID,
            VALID_DSN,
            target_website=TARGET_WEBSITE_ID,
            source_website=SOURCE_WEBSITE_ID,
            since_date=None,
            replace=True,
        )
        importer.replace_target_data.assert_called_once()

    @patch("apps.core.services.connection")
    @patch("apps.core.models.UmamiImportJob")
    @patch("apps.core.services.UmamiImporter")
    def test_connection_error_records_generic_message(
        self, mock_importer_cls: MagicMock, mock_model: MagicMock, _conn: MagicMock
    ) -> None:
        from apps.core.services import run_umami_import_job

        importer = mock_importer_cls.return_value
        # psycopg's text may embed host/credentials; it must not leak through.
        importer.connect.side_effect = ConnectionError("host=secret password=leak")

        run_umami_import_job(
            JOB_ID,
            VALID_DSN,
            target_website=TARGET_WEBSITE_ID,
            source_website=SOURCE_WEBSITE_ID,
            since_date=None,
            replace=False,
        )

        error_calls = [
            c
            for c in mock_model.objects.filter.return_value.update.call_args_list
            if c.kwargs.get("status") == "error"
        ]
        assert error_calls, "expected a status=error update"
        message = error_calls[0].kwargs.get("error_message")
        assert message == "Cannot connect to the source database."
        assert "secret" not in message
        assert "leak" not in message


# ---------------------------------------------------------------------------
# Service: start the job without persisting the DSN
# ---------------------------------------------------------------------------


class TestStartUmamiImportJob:
    @patch("apps.settings_app.services.threading.Thread")
    @patch("apps.settings_app.services.UmamiImportJob")
    def test_creates_job_starts_thread_and_hides_dsn(
        self, mock_model: MagicMock, mock_thread: MagicMock
    ) -> None:
        from apps.settings_app.services import start_umami_import_job

        mock_model.objects.create.return_value = MagicMock(id=JOB_ID)

        result = start_umami_import_job(
            user_id=ADMIN_USER_ID,
            target_website=TARGET_WEBSITE_ID,
            source_website=SOURCE_WEBSITE_ID,
            source_dsn=VALID_DSN,
            since_date=None,
            replace=False,
        )

        assert result["id"] == JOB_ID
        # The DSN must never reach the persisted row.
        create_kwargs = mock_model.objects.create.call_args.kwargs
        assert "source_dsn" not in create_kwargs
        assert VALID_DSN not in create_kwargs.values()
        # The thread is started, and the DSN is passed to it in-memory only.
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        assert VALID_DSN in mock_thread.call_args.kwargs["args"]


# ---------------------------------------------------------------------------
# Generic copier: events land with is_bot=False (Postgres-backed regression)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestImportGenericIsBotDefault:
    """Umami's ``website_event`` has no ``is_bot`` column, so the importer omits
    it from the INSERT. The destination column must supply ``false`` via its
    database default — otherwise the NOT NULL constraint aborts the whole import.

    This drives :meth:`UmamiImporter._import_generic` against the real test
    database (its INSERT and ``information_schema`` lookup both hit Postgres),
    feeding a synthetic, Umami-shaped source cursor.
    """

    def test_omitted_is_bot_defaults_to_false(self) -> None:
        from apps.core.models import WebsiteEvent
        from apps.core.services import UmamiImporter

        target_website = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        importer = UmamiImporter(
            VALID_DSN,
            source_website=SOURCE_WEBSITE_ID,
            target_website=target_website,
        )

        # Umami column shape: no is_bot/bot_reason; session_id drives visitor_key.
        columns = ["event_id", "website_id", "session_id", "created_at", "url_path", "event_type"]
        rows = [
            (
                event_id,
                SOURCE_WEBSITE_ID,
                str(uuid.uuid4()),
                datetime(2026, 5, 22, 3, 2, 52, tzinfo=UTC),
                "/content/learn-astrology/category/birth-chart/angles/descendant",
                1,
            )
        ]

        # _import_generic only iterates the cursor; a plain list suffices.
        importer._import_generic(iter(rows), columns, "website_event", MagicMock(), MagicMock())

        event = WebsiteEvent.objects.get(event_id=event_id)
        assert event.is_bot is False
        assert event.bot_reason is None
        # website_id is remapped onto the target, visitor_key derived from session.
        assert str(event.website_id) == target_website
        assert event.visitor_key

    def test_session_geo_device_normalized(self) -> None:
        """Geo/device columns (joined from `session`) are normalised to the live
        tracker's vocabulary as they're inserted."""
        from apps.core.models import WebsiteEvent
        from apps.core.services import UmamiImporter

        target_website = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        importer = UmamiImporter(
            VALID_DSN,
            source_website=SOURCE_WEBSITE_ID,
            target_website=target_website,
        )

        # Shape after the session LEFT JOIN: country/browser/os/device present.
        columns = [
            "event_id", "website_id", "session_id", "created_at", "url_path",
            "event_type", "country", "browser", "os", "device",
        ]
        rows = [
            (
                event_id,
                SOURCE_WEBSITE_ID,
                str(uuid.uuid4()),
                datetime(2026, 5, 22, 3, 2, 52, tzinfo=UTC),
                "/x",
                1,
                "us",       # → "US"
                "Chrome",   # → "Chrome" (already canonical)
                "macOS",    # → "Mac OS X"
                "laptop",   # → "desktop"
            )
        ]

        importer._import_generic(iter(rows), columns, "website_event", MagicMock(), MagicMock())

        event = WebsiteEvent.objects.get(event_id=event_id)
        assert event.country == "US"
        assert event.browser == "Chrome"
        assert event.os == "Mac OS X"
        assert event.device == "desktop"


# ---------------------------------------------------------------------------
# Query builder: enrich events with session geo/device (unit, no DB)
# ---------------------------------------------------------------------------


class TestBuildDataQuery:
    """`_build_data_query` LEFT JOINs `session` only for geo/device columns
    missing from the source `website_event` — so a denormalized source keeps the
    plain `SELECT *` (no regression, no duplicate-column hazard)."""

    @staticmethod
    def _importer():
        from apps.core.services import UmamiImporter

        return UmamiImporter(
            VALID_DSN, source_website=SOURCE_WEBSITE_ID, target_website=TARGET_WEBSITE_ID
        )

    def test_normalized_source_joins_session(self) -> None:
        importer = self._importer()
        cols = {
            "website_event": {"event_id", "website_id", "session_id", "created_at", "url_path"},
            "session": {"session_id", "country", "browser", "os", "device", "region", "city"},
        }
        with patch.object(type(importer), "_source_columns", side_effect=lambda _src, t: cols[t]):
            sql = importer._build_data_query(MagicMock(), "website_event", "events")
        assert "LEFT JOIN session s ON we.session_id = s.session_id" in sql
        assert "we.*, s.country, s.browser, s.os, s.device" in sql
        # WHERE is qualified with the `we.` alias to avoid ambiguity.
        assert f"we.website_id = '{SOURCE_WEBSITE_ID}'" in sql

    def test_denormalized_source_no_join(self) -> None:
        importer = self._importer()
        cols = {
            "website_event": {
                "event_id", "website_id", "session_id", "country", "browser", "os", "device",
            },
            "session": {"session_id", "country", "browser", "os", "device"},
        }
        with patch.object(type(importer), "_source_columns", side_effect=lambda _src, t: cols[t]):
            sql = importer._build_data_query(MagicMock(), "website_event", "events")
        assert sql.startswith("SELECT * FROM website_event")
        assert "JOIN" not in sql
        assert f"website_id = '{SOURCE_WEBSITE_ID}'" in sql

    def test_missing_session_table_no_join(self) -> None:
        importer = self._importer()
        cols = {
            "website_event": {"event_id", "website_id", "session_id", "url_path"},
            "session": set(),
        }
        with patch.object(type(importer), "_source_columns", side_effect=lambda _src, t: cols[t]):
            sql = importer._build_data_query(MagicMock(), "website_event", "events")
        assert sql.startswith("SELECT * FROM website_event")
        assert "JOIN" not in sql

    def test_non_events_table_unchanged(self) -> None:
        importer = self._importer()
        sql = importer._build_data_query(MagicMock(), "team", "teams")
        assert sql == "SELECT * FROM team"


class TestNormalizeGeoDevice:
    """Value normalization onto Mantecato's live (ua-parser) vocabulary."""

    @pytest.mark.parametrize(
        ("col", "value", "expected"),
        [
            ("country", "us", "US"),
            ("country", "IT", "IT"),
            ("device", "Laptop", "desktop"),
            ("device", "Mobile", "mobile"),
            ("device", "desktop", "desktop"),
            ("os", "macOS", "Mac OS X"),
            ("os", "Windows 10/11", "Windows"),
            ("os", "Windows 7", "Windows"),
            ("os", "ChromeOS", "Chrome OS"),
            ("os", "Android", "Android"),
            ("os", "Linux", "Linux"),
            ("browser", "Chrome", "Chrome"),
            ("browser", "Mobile Safari", "Mobile Safari"),
            # Umami's lower-case detect-browser codes fold onto ua-parser names so
            # imported rows merge with native ones in the breakdown.
            ("browser", "chrome", "Chrome"),
            ("browser", "ios", "Mobile Safari"),
            ("browser", "crios", "Chrome Mobile iOS"),
            ("browser", "edge-chromium", "Edge"),
            ("browser", "samsung", "Samsung Internet"),
            # Unmapped codes (e.g. bot UAs) pass through untouched.
            ("browser", "searchbot", "searchbot"),
            ("country", None, None),
        ],
    )
    def test_normalize(self, col: str, value: str | None, expected: str | None) -> None:
        from apps.core.services import UmamiImporter

        assert UmamiImporter._normalize_geo_device(col, value) == expected
