"""Download MaxMind GeoLite2-City database for IP geolocation.

Tries sources in order:
1. Custom URL (env GEO_DATABASE_URL)
2. MaxMind API (env MAXMIND_LICENSE_KEY)
3. Open-source redistribution on GitHub
"""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

_MAXMIND_URL = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz"
)
_REDIST_URL = (
    "https://raw.githubusercontent.com/GitSquared/node-geolite2-redist"
    "/master/redist/GeoLite2-City.tar.gz"
)
_DB_FILENAME = "GeoLite2-City.mmdb"


class Command(BaseCommand):
    """Download the MaxMind GeoLite2-City ``.mmdb`` database.

    The database is required by the tracker ingestion endpoint for
    IP-to-country/city resolution. Three download sources are tried in
    priority order:

    1. Custom URL via ``GEO_DATABASE_URL`` env var.
    2. MaxMind API via ``MAXMIND_LICENSE_KEY`` env var.
    3. Open-source redistribution on GitHub (no key required).
    """

    help = "Download the MaxMind GeoLite2-City database for IP geolocation."

    def add_arguments(self, parser):
        """Register the ``--output`` argument.

        Args:
            parser: The :class:`~argparse.ArgumentParser` to configure.
        """
        parser.add_argument(
            "--output",
            default=None,
            help="Output path (default: <project>/geo/GeoLite2-City.mmdb)",
        )

    def handle(self, *args, **options):
        """Download, extract, and save the GeoLite2-City database.

        Raises:
            CommandError: On download failure or if the ``.mmdb`` file
                cannot be found in the archive.
        """
        output = options["output"]
        if not output:
            output = str(Path(settings.BASE_DIR) / "geo" / _DB_FILENAME)

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = self._resolve_url()
        self.stdout.write(f"Downloading GeoLite2-City from {url[:80]}...")

        try:
            req = Request(url, headers={"User-Agent": "mantecato/3.0"})
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
        except Exception as exc:
            raise CommandError(f"Download failed: {exc}") from exc

        mmdb_data = self._extract_mmdb(data)
        output_path.write_bytes(mmdb_data)
        size_mb = len(mmdb_data) / 1024 / 1024
        self.stdout.write(
            self.style.SUCCESS(f"Saved {_DB_FILENAME} to {output_path} ({size_mb:.1f} MB)")
        )

    def _resolve_url(self) -> str:
        """Determine the download URL based on available environment variables.

        Priority order:
            1. ``GEO_DATABASE_URL`` -- direct URL to a ``.tar.gz`` or ``.mmdb``.
            2. ``MAXMIND_LICENSE_KEY`` -- constructs the official MaxMind API URL.
            3. Fallback to the GitHub redistribution (no key needed).

        Returns:
            The resolved download URL string.
        """
        custom = os.environ.get("GEO_DATABASE_URL", "").strip()
        if custom:
            return custom

        license_key = os.environ.get("MAXMIND_LICENSE_KEY", "").strip()
        if license_key:
            return _MAXMIND_URL.format(key=license_key)

        return _REDIST_URL

    def _extract_mmdb(self, tar_data: bytes) -> bytes:
        """Extract the ``.mmdb`` file from a tar.gz archive.

        If the data is not a valid tar.gz but looks like a raw ``.mmdb``
        file (detected by magic bytes or size heuristic), it is returned
        as-is.

        Args:
            tar_data: The raw bytes downloaded from the URL.

        Returns:
            The ``.mmdb`` file contents.

        Raises:
            CommandError: If no ``.mmdb`` file can be found or extracted.
        """
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_data), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith(".mmdb"):
                        f = tf.extractfile(member)
                        if f is not None:
                            return f.read()
        except tarfile.TarError:
            pass

        # Heuristic: if the data starts with the MMDB magic bytes or is
        # large enough to be a raw database file, treat it as-is.
        if tar_data[:4] == b"\xab\xcd\xefMaxMind"[:4] or len(tar_data) > 1_000_000:
            return tar_data

        raise CommandError("Could not find .mmdb file in downloaded archive.")
