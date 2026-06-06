"""GeoIP resolution — MaxMind GeoLite2-City with CDN header fallback.

Matches Umami's approach: first check CDN-injected location headers
(Cloudflare, Vercel, CloudFront), then fall back to a local MaxMind lookup.
Returns (country, region, city) or (None, None, None) on failure.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

# CDN-injected geolocation headers, checked in priority order.
# Each tuple is (country_header, region_header, city_header).
# The first CDN whose country header is present wins.
_CDN_HEADER_SETS = [
    # Cloudflare -- most common CDN, highest priority
    ("HTTP_CF_IPCOUNTRY", "HTTP_CF_REGION_CODE", "HTTP_CF_IPCITY"),
    # Vercel -- popular for Next.js deployments
    ("HTTP_X_VERCEL_IP_COUNTRY", "HTTP_X_VERCEL_IP_COUNTRY_REGION", "HTTP_X_VERCEL_IP_CITY"),
    # AWS CloudFront
    (
        "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
        "HTTP_CLOUDFRONT_VIEWER_COUNTRY_REGION",
        "HTTP_CLOUDFRONT_VIEWER_CITY",
    ),
]

# Lazy-loaded MaxMind reader. The ``_geoip_loaded`` flag prevents repeated
# load attempts when the database file is missing.
_geoip_reader = None
_geoip_loaded = False


def _get_reader():
    """Return a lazily-initialised MaxMind GeoLite2-City database reader.

    Looks for the database file at the path specified by the ``GEOIP_PATH``
    environment variable, or falls back to ``<BASE_DIR>/geo/GeoLite2-City.mmdb``.
    The reader is loaded once and cached for the process lifetime.

    If the database file is missing or cannot be opened, ``None`` is returned
    and all subsequent calls also return ``None`` without retrying.

    Returns:
        A ``geoip2.database.Reader`` instance, or ``None`` if the database
        is unavailable.
    """
    global _geoip_reader, _geoip_loaded
    if _geoip_loaded:
        return _geoip_reader

    _geoip_loaded = True
    db_path = os.environ.get("GEOIP_PATH", "")
    if not db_path:
        from django.conf import settings

        db_path = str(Path(settings.BASE_DIR) / "geo" / "GeoLite2-City.mmdb")

    if not Path(db_path).is_file():
        logger.info("GeoIP database not found at %s — geo fields will be NULL", db_path)
        return None

    try:
        import geoip2.database

        _geoip_reader = geoip2.database.Reader(db_path)
        logger.info("GeoIP database loaded from %s", db_path)
    except Exception:
        logger.warning("Failed to open GeoIP database at %s", db_path, exc_info=True)
    return _geoip_reader


def resolve_geo(request: HttpRequest, ip: str) -> tuple[str | None, str | None, str | None]:
    """Resolve the geographic location of a client IP address.

    Uses a two-tier strategy matching Umami's approach:

    1. **CDN headers (preferred):** Check for geo headers injected by
       Cloudflare, Vercel, or CloudFront. These are more accurate than
       local MaxMind lookups because CDNs resolve the IP at their edge.
    2. **MaxMind fallback:** If no CDN headers are found, perform a local
       lookup against the GeoLite2-City database.

    Both tiers return ISO standard codes:
    - ``country``: ISO 3166-1 alpha-2 (e.g. ``"US"``, ``"IT"``).
    - ``region``: ISO 3166-2 subdivision code (e.g. ``"CA"`` for California).
    - ``city``: City name as a string (e.g. ``"San Francisco"``).

    Args:
        request: The HTTP request containing potential CDN geo headers.
        ip: The resolved client IP address for MaxMind lookup.

    Returns:
        A 3-tuple ``(country, region, city)`` where each element is a
        string or ``None`` if resolution failed.
    """
    # Tier 1: check CDN-injected headers (no DB lookup needed)
    for country_h, region_h, city_h in _CDN_HEADER_SETS:
        country = request.META.get(country_h, "").strip() or None
        if country:
            region = request.META.get(region_h, "").strip() or None
            city = request.META.get(city_h, "").strip() or None
            return country, region, city

    # Tier 2: fall back to local MaxMind GeoLite2-City database
    reader = _get_reader()
    if reader is None or not ip:
        return None, None, None

    try:
        resp = reader.city(ip)
        country = resp.country.iso_code
        # subdivisions may be empty for some countries/IPs
        region = resp.subdivisions.most_specific.iso_code if resp.subdivisions else None
        city = resp.city.name
        return country, region, city
    except Exception:
        # Catch all MaxMind exceptions (AddressNotFoundError, invalid IPs, etc.)
        return None, None, None
