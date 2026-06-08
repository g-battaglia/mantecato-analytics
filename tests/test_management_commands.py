"""Tests for the ``createuser`` / ``createwebsite`` / ``downloadgeo`` /
``importumami`` management commands.

All tests run without ``django_db`` by mocking the ORM and the external
file-system / network side effects, so the suite stays fast and hermetic.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

# ============================================================================
# createuser
# ============================================================================


class TestCreateUserCommand:
    @patch("apps.core.management.commands.createuser.MantecatoUser")
    def test_creates_user(self, mock_model: MagicMock) -> None:
        mock_model.objects.filter.return_value.exists.return_value = False
        out = io.StringIO()
        call_command("createuser", "newuser", "--password", "secret", stdout=out)
        mock_model.objects.create_user.assert_called_once_with(
            username="newuser", password="secret", role="user"
        )
        assert "newuser" in out.getvalue()

    @patch("apps.core.management.commands.createuser.MantecatoUser")
    def test_admin_role(self, mock_model: MagicMock) -> None:
        mock_model.objects.filter.return_value.exists.return_value = False
        call_command(
            "createuser", "newadmin", "--password", "secret", "--role", "admin"
        )
        mock_model.objects.create_user.assert_called_once_with(
            username="newadmin", password="secret", role="admin"
        )

    @patch("apps.core.management.commands.createuser.MantecatoUser")
    def test_duplicate_user_raises(self, mock_model: MagicMock) -> None:
        mock_model.objects.filter.return_value.exists.return_value = True
        with pytest.raises(CommandError, match="already exists"):
            call_command("createuser", "dup", "--password", "secret")
        mock_model.objects.create_user.assert_not_called()

    @patch("apps.core.management.commands.createuser.MantecatoUser")
    def test_empty_username_raises(self, mock_model: MagicMock) -> None:
        with pytest.raises(CommandError, match="Username cannot be empty"):
            call_command("createuser", "  ", "--password", "secret")
        mock_model.objects.create_user.assert_not_called()

    @patch("apps.core.management.commands.createuser.MantecatoUser")
    def test_short_password_raises(self, mock_model: MagicMock) -> None:
        mock_model.objects.filter.return_value.exists.return_value = False
        with pytest.raises(CommandError, match="at least 4 characters"):
            call_command("createuser", "newuser", "--password", "x")
        mock_model.objects.create_user.assert_not_called()


# ============================================================================
# createwebsite
# ============================================================================


class TestCreateWebsiteCommand:
    @patch("apps.core.management.commands.createwebsite.Website")
    def test_creates_website(self, mock_model: MagicMock) -> None:
        site = MagicMock()
        site.id = "uuid-1"
        mock_model.objects.create.return_value = site
        out = io.StringIO()
        call_command("createwebsite", "--name", "My Site", "--domain", "x.com", stdout=out)
        mock_model.objects.create.assert_called_once_with(
            name="My Site", domain="x.com", user_id=None, team_id=None
        )
        assert "My Site" in out.getvalue()

    @patch("apps.core.management.commands.createwebsite.Website")
    def test_empty_name_raises(self, mock_model: MagicMock) -> None:
        with pytest.raises(CommandError, match="Name cannot be empty"):
            call_command("createwebsite", "--name", "  ")
        mock_model.objects.create.assert_not_called()


# ============================================================================
# downloadgeo
# ============================================================================


class TestDownloadGeoCommand:
    @patch("apps.core.management.commands.downloadgeo.urlopen")
    def test_extracts_mmdb_from_tar(
        self, mock_urlopen: MagicMock, tmp_path: object
    ) -> None:
        # Build a minimal tar.gz containing a fake .mmdb
        import gzip
        import tarfile

        body = io.BytesIO()
        with tarfile.open(fileobj=body, mode="w:gz") as tf:
            data = b"\xab\xcd\xefMaxMind-fake-payload" + b"X" * 100
            info = tarfile.TarInfo(name="GeoLite2-City_20240101/GeoLite2-City.mmdb")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        body.seek(0)

        mock_resp = MagicMock()
        mock_resp.read.return_value = body.getvalue()
        mock_resp.__enter__ = lambda self: self
        mock_resp.__exit__ = lambda *a: None
        mock_urlopen.return_value = mock_resp

        target = tmp_path / "geo" / "GeoLite2-City.mmdb"
        out = io.StringIO()
        call_command("downloadgeo", "--output", str(target), stdout=out)

        assert target.exists()
        assert "GeoLite2-City" in out.getvalue()
        # Use gzip to confirm the assertion-only path stays imported by Ruff
        # (no actual use; this keeps the import set lint-clean if reused).
        _ = gzip

    @patch("apps.core.management.commands.downloadgeo.urlopen")
    def test_download_failure_raises(
        self, mock_urlopen: MagicMock, tmp_path: object
    ) -> None:
        mock_urlopen.side_effect = Exception("network down")
        with pytest.raises(CommandError, match="Download failed"):
            call_command(
                "downloadgeo",
                "--output",
                str(tmp_path / "geo" / "G.mmdb"),
            )


# ============================================================================
# importumami (atomicity behaviour, dry-run path)
# ============================================================================


class TestImportUmamiCommand:
    @patch("apps.core.services.psycopg.connect")
    def test_dry_run_does_not_import(self, mock_connect: MagicMock) -> None:
        # Build a fake source connection / cursor that returns 0 for every count.
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0,)
        mock_cur.__enter__ = lambda self: self
        mock_cur.__exit__ = lambda *a: None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_connect.return_value = mock_conn

        # Should not raise and should not call execute besides the COUNTs.
        call_command(
            "importumami",
            "--source-db",
            "postgresql://test/x",
            "--include-config",
            "--noinput",
            "--confirm-replace-config",
            "--dry-run",
        )
        # Verify it asked for counts but never INSERTed.
        executed = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert all("COUNT(*)" in s for s in executed)

    @patch("apps.core.services.psycopg.connect")
    def test_bad_date_raises(self, mock_connect: MagicMock) -> None:
        with pytest.raises(CommandError, match="Invalid date format"):
            call_command(
                "importumami",
                "--source-db",
                "postgresql://test/x",
                "--include-config",
                "--noinput",
                "--confirm-replace-config",
                "--since",
                "nonsense",
            )
        mock_connect.assert_not_called()

    @patch("apps.core.services.psycopg.connect")
    def test_connection_failure_raises(self, mock_connect: MagicMock) -> None:
        mock_connect.side_effect = Exception("refused")
        with pytest.raises(CommandError, match="Cannot connect"):
            call_command(
                "importumami",
                "--source-db",
                "postgresql://test/x",
                "--include-config",
                "--noinput",
                "--confirm-replace-config",
            )


# ============================================================================
# importumamienv (deployment-time environment dispatcher)
# ============================================================================


class TestImportUmamiEnvCommand:
    @patch("apps.core.management.commands.importumamienv.call_command")
    def test_disabled_is_a_noop(self, mock_call_command: MagicMock) -> None:
        with patch.dict("os.environ", {"UMAMI_IMPORT_ON_DEPLOY": "False"}, clear=True):
            call_command("importumamienv")
        mock_call_command.assert_not_called()

    @patch("apps.core.management.commands.importumamienv.call_command")
    def test_data_import_uses_environment(self, mock_call_command: MagicMock) -> None:
        env = {
            "UMAMI_IMPORT_ON_DEPLOY": "True",
            "UMAMI_DATABASE_URL": "postgresql://source.example.invalid/umami",
            "UMAMI_IMPORT_MODE": "data",
            "UMAMI_SOURCE_WEBSITE_ID": "a0000000-0000-0000-0000-000000000001",
            "MANTECATO_TARGET_WEBSITE_ID": "b0000000-0000-0000-0000-000000000001",
            "UMAMI_IMPORT_SINCE": "2025-01-01",
        }
        with patch.dict("os.environ", env, clear=True):
            call_command("importumamienv")

        mock_call_command.assert_called_once_with(
            "importumamidata",
            source_db=env["UMAMI_DATABASE_URL"],
            source_website=env["UMAMI_SOURCE_WEBSITE_ID"],
            target_website=env["MANTECATO_TARGET_WEBSITE_ID"],
            since=env["UMAMI_IMPORT_SINCE"],
            noinput=True,
        )

    @patch("apps.core.management.commands.importumamienv.call_command")
    def test_full_import_requires_explicit_acknowledgement(
        self, mock_call_command: MagicMock
    ) -> None:
        env = {
            "UMAMI_IMPORT_ON_DEPLOY": "True",
            "UMAMI_DATABASE_URL": "postgresql://source.example.invalid/umami",
            "UMAMI_IMPORT_MODE": "full",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            pytest.raises(CommandError, match="UMAMI_IMPORT_ALLOW_CONFIG=True"),
        ):
            call_command("importumamienv")
        mock_call_command.assert_not_called()


