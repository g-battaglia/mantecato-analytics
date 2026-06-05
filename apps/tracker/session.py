"""Session resolution for the tracker — deterministic sessions and visits.

Both session_id and visit_id are deterministic UUIDs:
- session_id = uuid5(websiteId + IP + UA + monthly_salt)
- visit_id   = uuid5(session_id + hourly_salt)

The same browser+IP within a calendar month → same session_id.
The same session within a calendar hour → same visit_id.
A new visit_id is generated when the gap exceeds 30 minutes.

This matches Umami's approach and avoids count inflation when tokens
are lost (full-page navigation, cold starts, timeouts).
"""

from __future__ import annotations

import hashlib
import time
import uuid as uuid_mod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from django.core import signing
from django.utils import timezone

from core.mantecato_core.database import raw_query

# A visit expires after 30 minutes of inactivity, matching Umami's default.
# When the gap between the last event timestamp in the token and now exceeds
# this threshold, a new visit_id is generated (but session_id stays the same).
VISIT_TIMEOUT_SECONDS = 30 * 60

# Lazy-initialized singletons to avoid hitting Django settings at import time.
_SIGNER = None
_SECRET: str | None = None


def _get_signer():
    """Return a lazily-initialised Django ``Signer`` for session token signing.

    The signer uses ``:`` as separator (not the default ``:``) to produce
    tokens that are safe to embed in HTTP headers without encoding.

    Returns:
        A :class:`django.core.signing.Signer` instance, cached for the
        process lifetime.
    """
    global _SIGNER
    if _SIGNER is None:
        _SIGNER = signing.Signer(sep=":")
    return _SIGNER


def _get_secret() -> str:
    """Return the hashed SECRET_KEY used as an input to deterministic UUID generation.

    The raw ``SECRET_KEY`` is run through SHA-512 to produce a fixed-length
    secret that is mixed into all session/visit UUID computations. This
    ensures UUIDs cannot be predicted without knowing the server secret.

    Returns:
        A hex-encoded SHA-512 digest of ``settings.SECRET_KEY``.
    """
    global _SECRET
    if _SECRET is None:
        from django.conf import settings

        _SECRET = hashlib.sha512(settings.SECRET_KEY.encode()).hexdigest()
    return _SECRET


def _hash(*args: str) -> str:
    """Compute a SHA-512 hex digest of the concatenation of all arguments.

    Used as a building block for deterministic UUID generation and salt
    computation. The concatenation approach is safe here because the inputs
    are either fixed-format strings (ISO dates, UUIDs) or the server secret.

    Args:
        *args: Strings to concatenate and hash.

    Returns:
        A hex-encoded SHA-512 digest string.
    """
    return hashlib.sha512("".join(args).encode()).hexdigest()


# Hardcoded English weekday and month abbreviations to avoid locale-dependent
# formatting. The salt derivation must produce identical results regardless
# of the server's locale settings, so we cannot use strftime.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _to_utc_string(dt: datetime) -> str:
    """Format a datetime as a locale-independent UTC string.

    Matches JavaScript's ``Date.toUTCString()`` output.

    This must match Umami's salt derivation exactly so that session IDs are
    compatible across implementations. Using Python's ``strftime`` is unsafe
    here because its output depends on the system locale.

    Args:
        dt: A datetime object (expected to be UTC).

    Returns:
        A string like ``"Mon, 01 Jan 2024 00:00:00 GMT"``.
    """
    return (
        f"{_WEEKDAYS[dt.weekday()]}, {dt.day:02d} {_MONTHS[dt.month - 1]}"
        f" {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} GMT"
    )


def _monthly_salt(dt: datetime) -> str:
    """Generate a salt that rotates at the start of each calendar month (UTC).

    The salt is a SHA-512 hash of the first-of-month timestamp, ensuring
    that the same browser+IP combination produces different session IDs in
    different months. This bounds session lifetime to one calendar month
    and prevents indefinite tracking of returning visitors.

    Args:
        dt: A timezone-aware datetime (typically ``timezone.now()``).

    Returns:
        A hex-encoded SHA-512 digest representing this month's salt.
    """
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return _hash(_to_utc_string(start))


def _hourly_salt(dt: datetime) -> str:
    """Generate a salt that rotates at the start of each calendar hour (UTC).

    Used for visit_id computation. Within the same hour, the same session
    produces the same visit_id; a new hour triggers a new visit_id (unless
    the visit is still active per the 30-minute timeout).

    Args:
        dt: A timezone-aware datetime (typically ``timezone.now()``).

    Returns:
        A hex-encoded SHA-512 digest representing this hour's salt.
    """
    start = dt.replace(minute=0, second=0, microsecond=0)
    return _hash(_to_utc_string(start))


def _deterministic_uuid(*args: str) -> str:
    """Generate a deterministic UUID v5 from the given inputs mixed with the server secret.

    Uses ``uuid5(NAMESPACE_DNS, hash(args + secret))`` so that the same set
    of inputs always produces the same UUID, but the result cannot be
    predicted without access to the server's SECRET_KEY.

    Args:
        *args: Strings that form the identity of the entity (e.g. website_id,
            IP, user agent, salt for sessions; session_id + salt for visits).

    Returns:
        A UUID v5 string (lowercase, hyphenated).
    """
    return str(uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, _hash(*args, _get_secret())))


def _encode_token(session_id: str, visit_id: str) -> str:
    """Create a signed session token for the ``x-mantecato-session`` response header.

    The token carries the session_id, visit_id, and current Unix timestamp,
    signed with Django's ``Signer`` to prevent client-side tampering. The
    tracker JS stores this token and sends it back on subsequent requests
    to maintain session continuity without server-side session storage.

    Token format (before signing): ``"{session_id}|{visit_id}|{unix_ts}"``

    Args:
        session_id: The resolved session UUID.
        visit_id: The resolved visit UUID.

    Returns:
        A signed token string safe for use in HTTP headers.
    """
    payload = f"{session_id}|{visit_id}|{int(time.time())}"
    return _get_signer().sign(payload)


def _decode_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a session token from the client.

    Validates the cryptographic signature and extracts the session state.
    Returns ``None`` for any tampered, malformed, or missing token, which
    triggers fresh session resolution in :func:`resolve_session`.

    Args:
        token: The raw token string from the ``x-mantecato-session`` or
            ``x-umami-cache`` request header.

    Returns:
        A dict with ``session_id`` (str), ``visit_id`` (str), and
        ``timestamp`` (int, Unix epoch seconds) on success, or ``None``
        if the token is invalid.
    """
    try:
        payload = _get_signer().unsign(token)
        parts = payload.split("|")
        if len(parts) != 3:
            return None
        return {
            "session_id": parts[0],
            "visit_id": parts[1],
            "timestamp": int(parts[2]),
        }
    except (signing.BadSignature, ValueError):
        return None


def resolve_session(
    website_id: str,
    ip: str,
    ua: str,
    screen: str,
    language: str,
    session_header: str | None,
    device_info: dict[str, str | None],
    geo_info: tuple[str | None, str | None, str | None],
) -> tuple[str, str, str]:
    """Resolve or create a session and visit, returning IDs and a signed token.

    Session resolution follows a two-path algorithm:

    **Path A -- returning visitor (valid token in header):**
    The client sent a signed token from a previous request. The session_id
    is reused directly from the token. The visit_id is either reused (if
    the gap since the last event is under 30 minutes) or regenerated
    (deterministically from session_id + hourly salt).

    **Path B -- new visitor (no token or invalid token):**
    A deterministic session_id is computed from ``(website_id, IP, UA,
    monthly_salt)``, and a visit_id from ``(session_id, hourly_salt)``.
    A session row is inserted with ``ON CONFLICT DO NOTHING`` so that
    concurrent first-requests from the same fingerprint are idempotent.

    This approach avoids server-side session storage entirely -- all state
    is carried in the signed token or re-derivable from the fingerprint.

    Args:
        website_id: UUID of the tracked website.
        ip: Client IP address (used as part of the session fingerprint).
        ua: Raw User-Agent string (used as part of the session fingerprint).
        screen: Screen resolution string (e.g. ``"1920x1080"``).
        language: Browser language (e.g. ``"en-US"``).
        session_header: The ``x-mantecato-session`` or ``x-umami-cache``
            header value from the request, or ``None``.
        device_info: Parsed UA fields from :func:`~apps.tracker.ua.parse_user_agent`.
        geo_info: ``(country, region, city)`` from :func:`~apps.tracker.geo.resolve_geo`.

    Returns:
        A 3-tuple of ``(session_id, visit_id, token)`` where ``token`` is
        the signed session state to return in the response.
    """

    now = timezone.now()
    h_salt = _hourly_salt(now)

    # --- Path A: try to resume an existing session from the signed token ---
    if session_header:
        decoded = _decode_token(session_header)
        if decoded:
            now_ts = int(time.time())
            gap = now_ts - decoded["timestamp"]
            session_id = decoded["session_id"]
            # If the visitor was inactive for more than 30 minutes, start a
            # new visit within the same session. Otherwise reuse the visit_id.
            visit_id = (
                _deterministic_uuid(session_id, h_salt)
                if gap > VISIT_TIMEOUT_SECONDS
                else decoded["visit_id"]
            )
            token = _encode_token(session_id, visit_id)
            return session_id, visit_id, token

    # --- Path B: no valid token -- compute IDs from the fingerprint ---
    m_salt = _monthly_salt(now)
    # session_id is deterministic: same (website, IP, UA) within the same
    # calendar month always yields the same UUID.
    session_id = _deterministic_uuid(website_id, ip, ua, m_salt)
    visit_id = _deterministic_uuid(session_id, h_salt)
    country, region, city = geo_info

    # Upsert the session row. ON CONFLICT DO NOTHING handles the race where
    # two requests from the same new visitor arrive simultaneously.
    raw_query(
        """
        INSERT INTO session
            (session_id, website_id, browser, os, device, screen, language,
             country, region, city, created_at)
        VALUES
            ({{sessionId::uuid}}, {{websiteId::uuid}}, {{browser}}, {{os}},
             {{device}}, {{screen}}, {{language}}, {{country}}, {{region}},
             {{city}}, {{createdAt::timestamptz}})
        ON CONFLICT (session_id) DO NOTHING
        """,
        {
            "sessionId": session_id,
            "websiteId": website_id,
            "browser": device_info.get("browser"),
            "os": device_info.get("os"),
            "device": device_info.get("device"),
            "screen": screen,
            "language": language,
            "country": country,
            "region": region,
            "city": city,
            "createdAt": now,
        },
    )

    token = _encode_token(session_id, visit_id)
    return session_id, visit_id, token
