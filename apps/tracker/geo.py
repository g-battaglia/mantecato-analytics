"""GeoIP resolution — country-level only for privacy-first aggregate analytics.

Resolves only the ISO 3166-1 alpha-2 country code. Region and city are
intentionally excluded to prevent re-identification of individuals in
low-traffic scenarios (small towns + timestamp + URL path).

Uses CDN-injected headers first, then falls back to MaxMind GeoLite2-Country.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

_CDN_COUNTRY_HEADERS = [
    "HTTP_CF_IPCOUNTRY",
    "HTTP_X_VERCEL_IP_COUNTRY",
    "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
]

# Lazy-loaded MaxMind reader. The ``_geoip_loaded`` flag prevents repeated
# load attempts when the database file is missing.
_geoip_reader = None
_geoip_loaded = False


def _get_reader():
    global _geoip_reader, _geoip_loaded
    if _geoip_loaded:
        return _geoip_reader

    _geoip_loaded = True
    db_path = os.environ.get("GEOIP_PATH", "")
    if not db_path:
        from django.conf import settings

        base = Path(settings.BASE_DIR) / "geo"
        for name in ("GeoLite2-Country.mmdb", "GeoLite2-City.mmdb"):
            candidate = base / name
            if candidate.is_file():
                db_path = str(candidate)
                break
        if not db_path:
            db_path = str(base / "GeoLite2-Country.mmdb")

    if not Path(db_path).is_file():
        logger.info("GeoIP database not found at %s — country will be NULL", db_path)
        return None

    try:
        import geoip2.database

        _geoip_reader = geoip2.database.Reader(db_path)
        logger.info("GeoIP database loaded from %s", db_path)
    except Exception:
        logger.warning("Failed to open GeoIP database at %s", db_path, exc_info=True)
    return _geoip_reader


def resolve_geo(request: HttpRequest, ip: str) -> str | None:
    """Resolve only the ISO 3166-1 alpha-2 country code for a client IP.

    Region and city are intentionally not resolved to prevent
    re-identification in low-traffic scenarios.
    """
    for header in _CDN_COUNTRY_HEADERS:
        country = request.META.get(header, "").strip() or None
        if country:
            return country

    reader = _get_reader()
    if reader is None or not ip:
        return None

    try:
        resp = reader.country(ip)
        return resp.country.iso_code
    except Exception:
        return None
